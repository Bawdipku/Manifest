"""Transactional cargo workflows. All timestamps are ISO 8601 with an offset."""

import copy
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROLES = {"admin", "counter", "warehouse", "driver", "finance", "auditor", "partner"}
OPERATIONS = {
    "admin": {
        "sales",
        "cancel",
        "trip",
        "receipt",
        "pod",
        "report",
        "review",
        "assign",
        "soa",
        "invoice",
        "master",
        "accounts",
        "reports",
        "financial",
    },
    "counter": {"sales", "reports", "financial"},
    "warehouse": {"trip", "receipt", "pod", "report", "reports"},
    "driver": {"report"},
    "partner": {"report"},
    "finance": {"cancel", "soa", "invoice", "reports", "financial"},
    "auditor": {"reports", "financial"},
}
MASTER_TYPES = {
    "branches",
    "cities",
    "employees",
    "customers",
    "fleet",
    "rates",
    "products",
    "units",
    "vendors",
}


class Problem(Exception):
    def __init__(self, message, status=422):
        self.message, self.status = message, status


def require(condition, message, status=422):
    if not condition:
        raise Problem(message, status)


def now():
    return datetime.now(timezone.utc).isoformat()


def uid(prefix):
    return prefix + "-" + uuid.uuid4().hex[:12]


def text(p, k, required=True):
    v = str(p.get(k, "")).strip()
    require(not required or bool(v), "Wajib diisi: " + k)
    require(len(v) <= 5000, "Teks terlalu panjang: " + k)
    return v


def moment(v):
    try:
        d = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        require(d.tzinfo is not None, "Waktu harus menyertakan zona waktu.")
        require(
            d <= datetime.now(timezone.utc), "Waktu kejadian tidak boleh di masa depan."
        )
        return d
    except (ValueError, TypeError):
        raise Problem("Waktu tidak valid.")


def amount(v):
    try:
        n = int(v)
    except (ValueError, TypeError):
        raise Problem("Nilai rupiah harus bilangan bulat.")
    require(
        str(n) == str(v) or isinstance(v, int), "Nilai rupiah harus bilangan bulat."
    )
    require(0 <= n <= 10**12, "Nilai rupiah di luar batas.")
    return n


def item(rows, id):
    v = next((x for x in rows if x["id"] == id), None)
    require(v is not None, "Data tidak ditemukan.", 404)
    return v


def permissions(u, state):
    # Per-role templates are administered centrally; an empty template grants no operations.
    return (
        set(
            state.get("permission_templates", {}).get(
                u["role"], OPERATIONS.get(u["role"], set())
            )
        )
        if u["role"] != "admin"
        else OPERATIONS["admin"]
    )


def permit(u, state, op):
    require(op in permissions(u, state), "Akses tindakan ditolak.", 403)


def branch(u, b):
    return u["role"] == "admin" or b in u["branches"]


def at_branch(u, b):
    require(branch(u, b), "Cabang di luar cakupan akun.", 403)


def external(u):
    return u["role"] in ("driver", "partner")


def shipment_visible(u, s, state):
    if external(u):
        return s.get("assigned_to") == u["id"]
    if branch(u, s["origin"]) or branch(u, s["final_branch"]):
        return True
    return any(branch(u, l["origin"]) or branch(u, l["destination"]) for l in s["legs"])


def finance_visible(u, s, state):
    return (
        not external(u)
        and "financial" in permissions(u, state)
        and (branch(u, s["origin"]) or branch(u, s["final_branch"]))
    )


def current_location(s):
    if not s["legs"]:
        return s["origin"]
    last = s["legs"][-1]
    return last["destination"] if last.get("received_at") else last["origin"]


def pending(state, id):
    return any(
        r["shipment_id"] == id and r["status"] == "pending"
        for r in state["field_reports"]
    )


def latest(s):
    require(bool(s["legs"]), "Resi belum memiliki tahap perjalanan.")
    return s["legs"][-1]


def trip_for(state, leg):
    return item(state["trips"], leg["trip_id"])


def event_after(value, baseline):
    require(moment(value) >= moment(baseline), "Urutan waktu kejadian tidak konsisten.")


def active(s):
    require(
        s["status"] == "registered" and not s.get("pod"),
        "Resi dibatalkan, draft, atau sudah POD.",
    )


def trip_ships(state, t):
    return [item(state["shipments"], x) for x in t["shipment_ids"]]


def snapshot_sender(state, p):
    if p.get("customer_id"):
        c = item(state["masters"]["customers"], p["customer_id"])
        require(c.get("active", True), "Pelanggan tidak aktif.")
        return {
            "name": c["name"],
            "address": c.get("address", ""),
            "contact": c.get("contact", ""),
        }
    return {
        "name": text(p, "sender"),
        "address": text(p, "sender_address", False),
        "contact": text(p, "sender_contact", False),
    }


def init_state():
    return {
        "masters": {k: [] for k in MASTER_TYPES},
        "permission_templates": {},
        "shipments": [],
        "trips": [],
        "soa_groups": [],
        "field_reports": [],
        "returns": [],
        "invoices": [],
        "archives": [],
    }


def check_receipt(u, state, s, p):
    active(s)
    l = latest(s)
    t = trip_for(state, l)
    require(
        t["type"] == "P2P" and t["status"] == "departed",
        "Penerimaan hanya untuk trip P2P yang berangkat.",
    )
    at_branch(u, t["destination"])
    require(not l.get("received_at"), "Resi sudah diterima.")
    when = text(p, "occurred_at")
    event_after(when, t["departed_at"])
    if t["executor"] == "vendor":
        require(t.get("handover_at"), "Serah terima vendor belum dicatat.")
        event_after(when, t["handover_at"])
    return l, t, when


def receive(u, state, s, p):
    l, t, when = check_receipt(u, state, s, p)
    l.update(
        received_at=when,
        received_by=u["id"],
        received_recorded_at=now(),
        condition=text(p, "condition"),
        note=text(p, "note", False),
    )
    s["operational_status"] = "arrived"


def record_pod(u, state, s, p, evidence_ids):
    active(s)
    l = latest(s)
    t = trip_for(state, l)
    require(
        t["status"] == "departed" and t["type"] == "P2D",
        "POD hanya pada tahap P2D terakhir; tahap transit tidak boleh POD.",
    )
    at_branch(u, t["origin"])
    when = text(p, "occurred_at")
    event_after(when, t["departed_at"])
    if t["executor"] == "vendor":
        require(t.get("handover_at"), "Serah terima vendor belum dicatat.")
        event_after(when, t["handover_at"])
    require(
        evidence_ids or text(p, "exception_reason", False),
        "Bukti atau alasan pengecualian wajib diisi.",
    )
    s["pod"] = {
        "receiver": text(p, "receiver"),
        "occurred_at": when,
        "recorded_at": now(),
        "actor": u["id"],
        "evidence_ids": evidence_ids,
        "exception_reason": text(p, "exception_reason", False),
    }
    s["operational_status"] = "pod"
    s["document_status"] = "waiting_return"


def apply(u, state, action, p, evidence_ids=None):
    evidence_ids = evidence_ids or []
    stamp = now()
    role = u["role"]
    if action == "master.save":
        permit(u, state, "master")
        kind = text(p, "kind")
        require(kind in MASTER_TYPES, "Master tidak valid.")
        rows = state["masters"][kind]
        old = next((x for x in rows if x["id"] == p.get("id")), None)
        data = {k: v for k, v in p.items() if k not in ("kind", "id")}
        data["name"] = text(p, "name")
        data["id"] = old["id"] if old else uid(kind)
        data["active"] = bool(p.get("active", True))
        if kind == "branches":
            data["prefix"] = text(p, "prefix").upper()
            data["office_code"] = text(p, "office_code")
            data["city_code"] = text(p, "city_code")
            require(
                data["prefix"].isalnum() and len(data["prefix"]) <= 8,
                "Prefix barcode harus 1–8 huruf/angka ASCII.",
            )
            require(data["prefix"].isascii(), "Prefix harus ASCII.")
            require(
                not any(
                    x["id"] != data["id"] and x["prefix"] == data["prefix"]
                    for x in rows
                ),
                "Prefix cabang sudah dipakai.",
            )
        if old:
            old.update(data)
        else:
            rows.append(data)
        return data["id"]
    if action == "permissions.save":
        permit(u, state, "accounts")
        r = text(p, "role")
        require(r in ROLES and r != "admin", "Peran tidak valid.")
        ops = p.get("operations", [])
        require(
            isinstance(ops, list)
            and set(ops)
            <= set().union(*OPERATIONS.values())
            - {"accounts", "master", "review", "assign"},
            "Izin template tidak valid.",
        )
        require(
            not external({"role": r}) or set(ops) <= {"report"},
            "Akun lapangan hanya boleh mengirim laporan.",
        )
        state["permission_templates"][r] = ops
        return r
    if action == "shipment.save":
        permit(u, state, "sales")
        s = next((s for s in state["shipments"] if s["id"] == p.get("id")), None)
        if s:
            at_branch(u, s["origin"])
            require(s["status"] == "draft", "Hanya draft yang dapat diubah.")
        origin = text(p, "origin")
        at_branch(u, origin)
        b = item(state["masters"]["branches"], origin)
        dest = text(p, "final_branch")
        item(state["masters"]["branches"], dest)
        weights = float(p.get("weight", 0))
        packages = int(p.get("packages", 0))
        require(
            0 < weights < 10**7 and 0 < packages <= 10**6,
            "Koli dan berat harus positif.",
        )
        date = text(p, "ship_date")
        try:
            datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            raise Problem("Tanggal kirim tidak valid.")
        data = {
            "origin": origin,
            "destination": text(p, "destination"),
            "final_branch": dest,
            "customer_id": p.get("customer_id") or None,
            "sender": snapshot_sender(state, p),
            "receiver": text(p, "receiver"),
            "address": text(p, "address"),
            "contact": text(p, "contact", False),
            "description": text(p, "description", False),
            "reference": text(p, "reference", False),
            "packages": packages,
            "weight": weights,
            "ship_date": date,
            "values": {
                k: amount(p.get(k, 0))
                for k in ("cash", "credit", "collect", "forwarding")
            },
        }
        if s:
            s.update(data)
        else:
            s = {
                **data,
                "id": uid("SHP"),
                "number": None,
                "status": "draft",
                "legs": [],
                "created_at": stamp,
                "created_by": u["id"],
                "pod": None,
                "soa": None,
                "actual_soa": None,
                "soa_history": [],
                "assigned_to": None,
                "operational_status": "waiting",
                "document_status": "waiting_pod",
            }
            state["shipments"].append(s)
        if p.get("register"):
            d = datetime.now(ZoneInfo("Asia/Jakarta")).strftime("%y%m%d")
            prefix = b["prefix"] + "-" + d + "-"
            n = 1 + max(
                [
                    int(x["number"].split("-")[-1])
                    for x in state["shipments"]
                    if (x.get("number") or "").startswith(prefix)
                ]
                + [0]
            )
            s["number"] = prefix + str(n).zfill(6)
            s["status"] = "registered"
            s["registered_at"] = stamp
        return s["id"]
    if action == "shipment.cancel":
        s = item(state["shipments"], text(p, "id"))
        at_branch(u, s["origin"])
        permit(
            u,
            state,
            "cancel" if s["soa"] or "cancel" in permissions(u, state) else "sales",
        )
        require(s["status"] != "cancelled", "Resi sudah dibatalkan.")
        require(
            not any(
                s["id"] in i["shipment_ids"] and i["status"] != "cancelled"
                for i in state["invoices"]
            ),
            "Batalkan invoice aktif terlebih dahulu.",
        )
        require(
            not s["legs"]
            or all(trip_for(state, l)["status"] == "draft" for l in s["legs"]),
            "Resi yang sudah berangkat tidak boleh dibatalkan.",
        )
        s["cancellation"] = {"reason": text(p, "reason"), "at": stamp, "actor": u["id"]}
        s["status"] = "cancelled"
        for t in state["trips"]:
            t["shipment_ids"] = [x for x in t["shipment_ids"] if x != s["id"]]
        s["legs"] = []
        return s["id"]
    if action == "trip.create":
        permit(u, state, "trip")
        origin = text(p, "origin")
        at_branch(u, origin)
        item(state["masters"]["branches"], origin)
        typ = text(p, "type")
        require(typ in ("P2P", "P2D"), "Jenis trip tidak valid.")
        destination = text(p, "destination") if typ == "P2P" else origin
        item(state["masters"]["branches"], destination)
        executor = text(p, "executor")
        require(executor in ("internal", "vendor"), "Pelaksana tidak valid.")
        mode = text(p, "mode")
        require(mode in ("transit", "final"), "Tujuan tahap tidak valid.")
        if executor == "vendor":
            item(state["masters"]["vendors"], text(p, "vendor_id"))
            text(p, "vendor_reference")
        vehicle = text(p, "vehicle", False)
        if p.get("fleet_id"):
            vehicle = item(state["masters"]["fleet"], p["fleet_id"]).get("plate", "")
        require(vehicle, "Nomor polisi wajib diisi.")
        t = {
            "id": uid("TRP"),
            "origin": origin,
            "destination": destination,
            "type": typ,
            "mode": mode,
            "executor": executor,
            "vendor_id": p.get("vendor_id"),
            "vendor_reference": p.get("vendor_reference", ""),
            "driver": text(p, "driver"),
            "vehicle": vehicle,
            "planned_date": text(p, "planned_date"),
            "status": "draft",
            "shipment_ids": [],
            "created_at": stamp,
        }
        state["trips"].append(t)
        return t["id"]
    if action in ("trip.add", "trip.remove", "trip.depart", "trip.handover"):
        permit(u, state, "trip")
        t = item(state["trips"], text(p, "id"))
        at_branch(u, t["origin"])
        if action == "trip.handover":
            require(
                t["executor"] == "vendor" and t["status"] == "departed",
                "Serah terima hanya untuk trip vendor berangkat.",
            )
            require(not t.get("handover_at"), "Serah terima sudah tercatat.")
            when = text(p, "occurred_at")
            event_after(when, t["departed_at"])
            t.update(
                handover_at=when,
                handover_recorded_at=stamp,
                handover_actor=u["id"],
                handover_reference=text(p, "reference"),
            )
            return t["id"]
        require(
            t["status"] == "draft", "Muatan trip yang berangkat tidak dapat diubah."
        )
        if action == "trip.add":
            ids = p.get("shipment_ids", [])
            require(
                isinstance(ids, list)
                and 1 <= len(ids) <= 200
                and len(ids) == len(set(ids)),
                "Tambahkan 1–200 resi unik.",
            )
            ships = [item(state["shipments"], x) for x in ids]
            for s in ships:
                active(s)
                require(
                    not pending(state, s["id"]),
                    "Laporan mitra masih menunggu verifikasi.",
                )
                require(
                    current_location(s) == t["origin"],
                    "Resi tidak berada di cabang asal trip.",
                )
                require(
                    not s["legs"] or bool(latest(s).get("received_at")),
                    "Resi belum diterima atau terikat trip aktif.",
                )
                if t["type"] == "P2P" and t["mode"] == "final":
                    require(
                        s["final_branch"] == t["destination"],
                        "Cabang tujuan akhir tidak cocok.",
                    )
                if t["type"] == "P2D":
                    require(
                        s["final_branch"] == t["origin"],
                        "P2D hanya dari cabang tujuan akhir.",
                    )
            for s in ships:
                s["legs"].append(
                    {
                        "trip_id": t["id"],
                        "origin": t["origin"],
                        "destination": t["destination"],
                        "assigned_at": stamp,
                    }
                )
                t["shipment_ids"].append(s["id"])
                s["operational_status"] = "waiting"
        elif action == "trip.remove":
            s = item(state["shipments"], text(p, "shipment_id"))
            text(p, "reason")
            require(latest(s)["trip_id"] == t["id"], "Resi tidak ada dalam trip ini.")
            s["legs"].pop()
            t["shipment_ids"].remove(s["id"])
            s["operational_status"] = "arrived" if s["legs"] else "waiting"
        else:
            when = text(p, "occurred_at")
            moment(when)
            ships = trip_ships(state, t)
            require(ships, "Trip tanpa muatan tidak boleh berangkat.")
            for s in ships:
                require(
                    s["soa"] and s["soa"]["confirmed"],
                    "SOA sementara semua resi harus terkonfirmasi.",
                )
                require(not pending(state, s["id"]), "Laporan menunggu verifikasi.")
                if len(s["legs"]) > 1:
                    event_after(when, s["legs"][-2]["received_at"])
            t.update(
                status="departed",
                departed_at=when,
                departure_recorded_at=stamp,
                departure_actor=u["id"],
            )
            for s in ships:
                latest(s)["departed_at"] = when
                s.setdefault("first_departed_at", when)
                s["operational_status"] = (
                    "delivering" if t["type"] == "P2D" else "in_transit"
                )
        return t["id"]
    if action == "receipt.record":
        permit(u, state, "receipt")
        s = item(state["shipments"], text(p, "id"))
        require(
            not pending(state, s["id"]),
            "Verifikasi laporan yang menunggu terlebih dahulu.",
        )
        receive(u, state, s, p)
        return s["id"]
    if action == "pod.record":
        permit(u, state, "pod")
        s = item(state["shipments"], text(p, "id"))
        require(
            not pending(state, s["id"]),
            "Verifikasi laporan yang menunggu terlebih dahulu.",
        )
        record_pod(u, state, s, p, evidence_ids)
        return s["id"]
    if action == "assignment.save":
        permit(u, state, "assign")
        require(role == "admin", "Penugasan hanya administrator.", 403)
        s = item(state["shipments"], text(p, "id"))
        s["assigned_to"] = p.get("user_id") or None
        s["assignment_at"] = stamp
        return s["id"]
    if action == "field.submit":
        permit(u, state, "report")
        s = item(state["shipments"], text(p, "shipment_id"))
        require(
            shipment_visible(u, s, state),
            "Resi tidak ditugaskan atau di luar cakupan.",
            403,
        )
        active(s)
        require(
            not pending(state, s["id"]), "Masih ada laporan menunggu untuk resi ini."
        )
        kind = text(p, "kind")
        require(kind in ("arrival", "pod", "issue"), "Jenis laporan tidak valid.")
        when = text(p, "occurred_at")
        moment(when)
        if external(u):
            require(
                s.get("assigned_to") == u["id"],
                "Resi tidak ditugaskan kepada Anda.",
                403,
            )
        r = {
            "id": uid("RPT"),
            "shipment_id": s["id"],
            "kind": kind,
            "status": "pending",
            "occurred_at": when,
            "recorded_at": stamp,
            "recorded_by": u["id"],
            "reporter": text(p, "reporter"),
            "contact": text(p, "contact"),
            "source": text(p, "source"),
            "note": text(p, "note", False),
            "receiver": text(p, "receiver", False),
            "condition": text(p, "condition", False),
            "evidence_ids": evidence_ids,
            "assigned_to_at_submission": s.get("assigned_to"),
        }
        state["field_reports"].append(r)
        return r["id"]
    if action == "field.review":
        permit(u, state, "review")
        require(role == "admin", "Verifikasi hanya administrator.", 403)
        r = item(state["field_reports"], text(p, "id"))
        s = item(state["shipments"], r["shipment_id"])
        require(r["status"] == "pending", "Laporan sudah diverifikasi.")
        decision = text(p, "decision")
        require(decision in ("approved", "rejected"), "Keputusan tidak valid.")
        reason = text(p, "reason")
        if decision == "approved":
            if r["kind"] == "pod":
                require(r["evidence_ids"], "Persetujuan POD wajib memiliki bukti.")
                record_pod(u, state, s, r, r["evidence_ids"])
            if r["kind"] == "arrival":
                receive(u, state, s, r)
            if r["kind"] == "issue":
                r["issue_open"] = True
        r.update(
            status=decision,
            reviewed_by=u["id"],
            reviewed_at=stamp,
            review_reason=reason,
        )
        return r["id"]
    if action == "field.resolve":
        permit(u, state, "review")
        r = item(state["field_reports"], text(p, "id"))
        require(r.get("issue_open"), "Kendala tidak terbuka.")
        r.update(issue_open=False, resolution=text(p, "reason"), resolved_at=stamp)
        return r["id"]
    if action == "soa.confirm":
        permit(u, state, "soa")
        t = item(state["trips"], text(p, "trip_id"))
        at_branch(u, t["origin"])
        dest = text(p, "destination")
        ships = [
            s
            for s in trip_ships(state, t)
            if s["destination"] == dest and len(s["legs"]) == 1
        ]
        require(ships, "Kelompok trip/DEST awal tidak ditemukan.")
        values = p.get("amounts", {})
        require(
            set(values) == {s["id"] for s in ships},
            "Isi nilai SOA setiap resi dalam kelompok.",
        )
        policy = text(p, "policy")
        provisional = bool(p.get("provisional"))
        group = next(
            (
                g
                for g in state["soa_groups"]
                if g["trip_id"] == t["id"] and g["destination"] == dest
            ),
            None,
        )
        if group:
            text(p, "reason")
        require(
            t["status"] == "draft",
            "SOA awal hanya dikonfirmasi/direvisi sebelum berangkat.",
        )
        version = 1 + len(group["versions"]) if group else 1
        snap = {
            "version": version,
            "policy": policy,
            "provisional": provisional,
            "amounts": {k: amount(v) for k, v in values.items()},
            "at": stamp,
            "actor": u["id"],
            "reason": p.get("reason", ""),
        }
        if not group:
            group = {
                "id": uid("SOA"),
                "trip_id": t["id"],
                "destination": dest,
                "versions": [],
            }
            state["soa_groups"].append(group)
        group["versions"].append(snap)
        for s in ships:
            if s["soa"]:
                s["soa_history"].append(copy.deepcopy(s["soa"]))
            s["soa"] = {
                "group_id": group["id"],
                "value": snap["amounts"][s["id"]],
                "version": version,
                "policy": policy,
                "provisional": provisional,
                "confirmed": True,
                "at": stamp,
            }
        return group["id"]
    if action in ("soa.actual", "soa.resolve", "soa.approve_policy"):
        permit(u, state, "soa")
        s = item(state["shipments"], text(p, "id"))
        require(finance_visible(u, s, state), "Data keuangan di luar cakupan.", 403)
        require(s["soa"], "SOA sementara belum tersedia.")
        if action == "soa.approve_policy":
            require(role == "admin", "Persetujuan kebijakan hanya administrator.", 403)
            s["soa_history"].append(copy.deepcopy(s["soa"]))
            s["soa"] = {
                **s["soa"],
                "provisional": False,
                "policy_approval": {
                    "reason": text(p, "reason"),
                    "at": stamp,
                    "actor": u["id"],
                },
            }
            return s["id"]
        require(s["pod"], "SOA asli hanya setelah POD.")
        if action == "soa.actual":
            if s["actual_soa"]:
                text(p, "reason")
                s.setdefault("actual_history", []).append(
                    copy.deepcopy(s["actual_soa"])
                )
            value = amount(p.get("value"))
            s["actual_soa"] = {
                "value": value,
                "at": stamp,
                "actor": u["id"],
                "reason": p.get("reason", ""),
                "status": (
                    "match"
                    if value == s["soa"]["value"] and not s["soa"]["provisional"]
                    else "difference"
                ),
            }
        else:
            require(s["actual_soa"], "SOA asli belum dicatat.")
            require(
                not s["soa"]["provisional"], "Kebijakan provisional harus disetujui."
            )
            s["actual_soa"].update(
                status="resolved",
                resolution=text(p, "reason"),
                resolved_at=stamp,
                resolved_by=u["id"],
            )
        return s["id"]
    if action == "return.create":
        permit(u, state, "receipt")
        ids = p.get("shipment_ids", [])
        require(ids and len(ids) == len(set(ids)), "Pilih resi unik.")
        ships = [item(state["shipments"], x) for x in ids]
        for s in ships:
            at_branch(u, s["final_branch"])
            require(
                s["pod"] and s["document_status"] in ("waiting_return", "problem"),
                "Dokumen belum tersedia atau sudah dalam batch.",
            )
        require(
            len({s["origin"] for s in ships}) == 1, "Satu batch untuk satu cabang asal."
        )
        r = {
            "id": uid("RET"),
            "reference": text(p, "reference"),
            "shipment_ids": ids,
            "destination": ships[0]["origin"],
            "created_at": stamp,
            "created_by": u["id"],
            "status": "returning",
        }
        state["returns"].append(r)
        for s in ships:
            s["document_status"] = "returning"
        return r["id"]
    if action in ("return.receive", "return.problem"):
        permit(u, state, "receipt")
        r = item(state["returns"], text(p, "id"))
        at_branch(u, r["destination"])
        require(r["status"] == "returning", "Batch tidak dalam pengembalian.")
        r.update(
            status="received" if action == "return.receive" else "problem",
            note=text(p, "note"),
            at=stamp,
            actor=u["id"],
        )
        for id in r["shipment_ids"]:
            item(state["shipments"], id)["document_status"] = (
                "received_origin" if action == "return.receive" else "problem"
            )
        return r["id"]
    if action == "invoice.create":
        permit(u, state, "invoice")
        ids = p.get("shipment_ids", [])
        require(ids and len(ids) == len(set(ids)), "Pilih resi unik.")
        ships = [item(state["shipments"], x) for x in ids]
        for s in ships:
            require(finance_visible(u, s, state), "Data di luar cakupan.", 403)
            require(
                s["status"] == "registered"
                and s["values"]["credit"] > 0
                and s["customer_id"],
                "Resi terdaftar berkredit dan pelanggan terdaftar wajib dipilih.",
            )
            require(
                not any(
                    s["id"] in i["shipment_ids"] and i["status"] != "cancelled"
                    for i in state["invoices"]
                ),
                "Resi sudah diklaim invoice aktif.",
            )
        require(
            len({s["customer_id"] for s in ships}) == 1
            and len({s["origin"] for s in ships}) == 1,
            "Invoice harus satu pelanggan dan cabang.",
        )
        i = {
            "id": uid("INV"),
            "origin": ships[0]["origin"],
            "customer_id": ships[0]["customer_id"],
            "shipment_ids": ids,
            "status": "draft",
            "created_at": stamp,
            "payments": [],
        }
        state["invoices"].append(i)
        return i["id"]
    if action.startswith("invoice.") or action.startswith("payment."):
        permit(u, state, "invoice")
        i = item(state["invoices"], text(p, "id"))
        at_branch(u, i["origin"])
        if action == "invoice.issue":
            require(i["status"] == "draft", "Invoice bukan draft.")
            ships = [item(state["shipments"], x) for x in i["shipment_ids"]]
            require(
                all(s["status"] == "registered" for s in ships), "Ada resi dibatalkan."
            )
            i.update(
                status="issued",
                issued_at=stamp,
                customer_snapshot=copy.deepcopy(
                    item(state["masters"]["customers"], i["customer_id"])
                ),
                lines=[
                    {
                        "shipment_id": s["id"],
                        "number": s["number"],
                        "value": s["values"]["credit"],
                    }
                    for s in ships
                ],
                total=sum(s["values"]["credit"] for s in ships),
            )
        elif action == "invoice.cancel":
            require(
                not any(not pay.get("reversed") for pay in i["payments"]),
                "Balikkan pembayaran sebelum membatalkan invoice.",
            )
            require(i["status"] != "cancelled", "Invoice sudah batal.")
            i.update(status="cancelled", reason=text(p, "reason"), cancelled_at=stamp)
        elif action == "payment.record":
            require(i["status"] == "issued", "Invoice belum diterbitkan.")
            value = amount(p.get("value"))
            paid = sum(x["value"] for x in i["payments"] if not x.get("reversed"))
            require(
                value > 0 and value <= i["total"] - paid,
                "Pembayaran melebihi saldo atau tidak positif.",
            )
            ref = text(p, "reference")
            require(
                not any(x["reference"] == ref for x in i["payments"]),
                "Referensi pembayaran sudah digunakan.",
            )
            when = text(p, "occurred_at")
            moment(when)
            i["payments"].append(
                {
                    "id": uid("PAY"),
                    "value": value,
                    "reference": ref,
                    "occurred_at": when,
                    "recorded_at": stamp,
                    "actor": u["id"],
                }
            )
        elif action == "payment.reverse":
            pay = item(i["payments"], text(p, "payment_id"))
            require(not pay.get("reversed"), "Pembayaran sudah dibalik.")
            pay.update(
                reversed=True,
                reversal_reason=text(p, "reason"),
                reversed_at=stamp,
                reversed_by=u["id"],
            )
        else:
            raise Problem("Tindakan tidak dikenal.", 404)
        return i["id"]
    if action == "report.archive":
        permit(u, state, "reports")
        require(role in ("admin", "finance"), "Arsip hanya administrator/finance.", 403)
        rows = report_rows(u, state, p)
        a = {
            "id": uid("ARC"),
            "actor": u["id"],
            "created_at": stamp,
            "branches": u["branches"],
            "filters": p,
            "rows": copy.deepcopy(rows),
        }
        state["archives"].append(a)
        return a["id"]
    raise Problem("Tindakan tidak dikenal.", 404)


def report_rows(u, state, filters):
    permit(u, state, "reports")
    view = filters.get("view", "sales")
    require(
        view
        in ("sales", "departed", "reconciliation", "cancelled", "finance", "documents"),
        "Jenis laporan tidak valid.",
    )
    query = str(filters.get("q", "")).lower()
    rows = []
    if view == "finance":
        permit(u, state, "financial")
        for invoice in state["invoices"]:
            if invoice["status"] != "issued" or not branch(u, invoice["origin"]):
                continue
            if filters.get("branch") and invoice["origin"] != filters["branch"]:
                continue
            day = (
                datetime.fromisoformat(invoice["issued_at"])
                .astimezone(ZoneInfo("Asia/Jakarta"))
                .date()
                .isoformat()
            )
            if (
                filters.get("from")
                and day < filters["from"]
                or filters.get("to")
                and day > filters["to"]
            ):
                continue
            if (
                query
                and query not in invoice["id"].lower()
                and not any(
                    query in line["number"].lower() for line in invoice["lines"]
                )
            ):
                continue
            paid = sum(x["value"] for x in invoice["payments"] if not x.get("reversed"))
            settlement = (
                "paid" if paid == invoice["total"] else "partial" if paid else "unpaid"
            )
            if filters.get("status") and filters["status"] != settlement:
                continue
            rows.append(
                {
                    "number": invoice["id"],
                    "date": day,
                    "origin": invoice["origin"],
                    "destination": invoice["customer_snapshot"]["name"],
                    "status": settlement,
                    "sales_status": "registered",
                    "document_status": "",
                    "invoice_total": invoice["total"],
                    "paid": paid,
                    "balance": invoice["total"] - paid,
                }
            )
        return rows
    for s in state["shipments"]:
        if not shipment_visible(u, s, state):
            continue
        if view != "documents" and not finance_visible(u, s, state):
            continue
        if filters.get("branch") and s["origin"] != filters["branch"]:
            continue
        if query and query not in (s.get("number") or "").lower():
            continue
        if s["status"] == "draft":
            continue
        if view == "cancelled" and s["status"] != "cancelled":
            continue
        if view != "cancelled" and s["status"] == "cancelled":
            continue
        if view == "departed" and not s.get("first_departed_at"):
            continue
        if view == "reconciliation" and not s["actual_soa"]:
            continue
        if filters.get("status") and filters["status"] not in (
            s["status"],
            s["operational_status"],
            s["document_status"],
            (s["actual_soa"] or {}).get("status"),
        ):
            continue
        time = (
            s.get("first_departed_at")
            if view in ("departed", "reconciliation")
            else s.get("registered_at", s["created_at"])
        )
        day = (
            datetime.fromisoformat(time)
            .astimezone(ZoneInfo("Asia/Jakarta"))
            .date()
            .isoformat()
        )
        if (
            filters.get("from")
            and day < filters["from"]
            or filters.get("to")
            and day > filters["to"]
        ):
            continue
        row = {
            "number": s["number"],
            "date": day,
            "origin": s["origin"],
            "destination": s["destination"],
            "status": s["operational_status"],
            "document_status": s["document_status"],
            "sales_status": s["status"],
            "reconciliation": (s["actual_soa"] or {}).get("status", ""),
        }
        if finance_visible(u, s, state):
            row.update(
                **s["values"],
                revenue=s["values"]["cash"]
                + s["values"]["credit"]
                + s["values"]["collect"],
                soa_temporary=(s["soa"] or {}).get("value", 0),
                soa_actual=(s["actual_soa"] or {}).get("value", 0)
            )
        rows.append(row)
    return rows


def view_state(u, state):
    result = copy.deepcopy(state)
    visible = [s for s in state["shipments"] if shipment_visible(u, s, state)]
    ids = {s["id"] for s in visible}
    result["shipments"] = copy.deepcopy(visible)
    for s in result["shipments"]:
        if not finance_visible(u, s, state):
            for k in (
                "values",
                "soa",
                "soa_history",
                "actual_soa",
                "actual_history",
                "customer_id",
            ):
                s.pop(k, None)
    tripids = {l["trip_id"] for s in visible for l in s["legs"]}
    result["trips"] = [
        copy.deepcopy(t)
        for t in state["trips"]
        if (not external(u) and (branch(u, t["origin"]) or branch(u, t["destination"])))
        or t["id"] in tripids
    ]
    for t in result["trips"]:
        t["shipment_ids"] = [id for id in t["shipment_ids"] if id in ids]
    result["field_reports"] = [
        r for r in state["field_reports"] if r["shipment_id"] in ids
    ]
    result["returns"] = [
        r
        for r in state["returns"]
        if not external(u)
        and (branch(u, r["destination"]) or all(id in ids for id in r["shipment_ids"]))
    ]
    result["invoices"] = [
        i
        for i in state["invoices"]
        if not external(u)
        and "financial" in permissions(u, state)
        and branch(u, i["origin"])
    ]
    result["soa_groups"] = [
        g
        for g in state["soa_groups"]
        if not external(u)
        and "financial" in permissions(u, state)
        and branch(u, item(state["trips"], g["trip_id"])["origin"])
    ]
    result["archives"] = [
        a
        for a in state["archives"]
        if not external(u)
        and "financial" in permissions(u, state)
        and all(branch(u, r["origin"]) for r in a["rows"])
        and (a["actor"] == u["id"] or u["role"] == "admin")
    ]
    if external(u):
        result["masters"] = {
            "branches": [
                {"id": b["id"], "name": b["name"]} for b in state["masters"]["branches"]
            ]
        }
        result["trips"] = []
        result["returns"] = []
    elif u["role"] != "admin":
        result["masters"] = {
            k: v
            for k, v in result["masters"].items()
            if k in ("branches", "cities", "products", "units", "fleet", "vendors")
            or k in ("customers", "rates")
            and "financial" in permissions(u, state)
        }
    if u["role"] != "admin":
        result["permission_templates"] = {}
    return result
