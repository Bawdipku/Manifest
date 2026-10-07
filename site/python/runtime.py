"""Public browser demo. No real authentication; all records stay in this browser."""

import base64, copy, hashlib, io, json, re, zipfile
from datetime import datetime, timedelta, timezone
from html import escape
from urllib.parse import urlparse, parse_qs
from backend.domain import *
from backend.printing import render_document

D = None


def demo_seed():
    global D
    admin = {
        "id": "demo-admin",
        "username": "admin",
        "name": "Administrator Demo",
        "role": "admin",
        "branches": [],
        "active": True,
        "vendor_id": None,
    }
    D = {
        "schema": 1,
        "state": init_state(),
        "accounts": [admin],
        "user_id": admin["id"],
        "revision": 0,
        "audit": [],
        "requests": {},
        "evidence": {},
    }

    def command(action, p):
        return apply(admin, D["state"], action, p)

    branches = []
    for prefix, name in [("PKU", "Pekanbaru"), ("HUB", "Hub Dumai"), ("BTM", "Batam")]:
        branches.append(
            command(
                "master.save",
                {
                    "kind": "branches",
                    "name": name,
                    "prefix": prefix,
                    "office_code": prefix,
                    "city_code": prefix,
                },
            )
        )
    a, b, d = branches
    customer = command(
        "master.save",
        {
            "kind": "customers",
            "name": "PT Contoh Niaga · DEMO",
            "address": "Alamat contoh, Pekanbaru",
            "contact": "000-DEMO",
        },
    )
    command(
        "master.save",
        {
            "kind": "fleet",
            "name": "Truk Demo 01",
            "plate": "BM DEMO 01",
            "capacity": "4 ton",
        },
    )
    vendor = command(
        "master.save",
        {"kind": "vendors", "name": "Vendor Contoh · DEMO", "contact": "000-DEMO"},
    )
    for kind, name in [
        ("cities", "Batam"),
        ("cities", "Pekanbaru"),
        ("employees", "Petugas Contoh"),
        ("products", "Cargo darat"),
        ("units", "Koli"),
        ("rates", "Tarif contoh"),
    ]:
        command("master.save", {"kind": kind, "name": name})
    D["accounts"].extend(
        [
            {
                "id": "demo-hub",
                "username": "gudang",
                "name": "Operasional Hub · Demo",
                "role": "warehouse",
                "branches": [b],
                "active": True,
                "vendor_id": None,
            },
            {
                "id": "demo-finance",
                "username": "finance",
                "name": "Finance · Demo",
                "role": "finance",
                "branches": [a, d],
                "active": True,
                "vendor_id": None,
            },
            {
                "id": "demo-partner",
                "username": "mitra",
                "name": "Mitra · Demo",
                "role": "partner",
                "branches": [d],
                "active": True,
                "vendor_id": vendor,
            },
        ]
    )

    def when(h):
        return (
            datetime.now(timezone.utc) - timedelta(days=3) + timedelta(hours=h)
        ).isoformat()

    def sale(receiver, register=True):
        return command(
            "shipment.save",
            {
                "origin": a,
                "final_branch": d,
                "destination": "Batam",
                "customer_id": customer,
                "receiver": receiver + " · DEMO",
                "address": "Jl. Contoh No. 1 (data fiktif)",
                "contact": "000-DEMO",
                "description": "Barang contoh",
                "reference": "DATA DEMO",
                "packages": 3,
                "weight": 24,
                "ship_date": datetime.now(ZoneInfo("Asia/Jakarta")).date().isoformat(),
                "cash": 25000,
                "credit": 250000,
                "collect": 0,
                "forwarding": 15000,
                "register": register,
            },
        )

    def make_trip(origin, destination, kind="P2P", mode="transit"):
        return command(
            "trip.create",
            {
                "origin": origin,
                "destination": destination,
                "type": kind,
                "mode": mode,
                "executor": "internal",
                "driver": "Pengemudi Demo",
                "vehicle": "BM DEMO 01",
                "planned_date": datetime.now(ZoneInfo("Asia/Jakarta"))
                .date()
                .isoformat(),
            },
        )

    fresh = sale("Siap dimanifestkan")
    waiting = sale("Menunggu penerimaan hub")
    ready_pod = sale("Siap POD penerima")
    completed = sale("Menunggu rekonsiliasi")
    draft = sale("Draft penjualan", False)
    first = make_trip(a, b)
    command("trip.add", {"id": first, "shipment_ids": [waiting, ready_pod, completed]})
    command(
        "soa.confirm",
        {
            "trip_id": first,
            "destination": "Batam",
            "amounts": {waiting: 75000, ready_pod: 80000, completed: 85000},
            "policy": "Kebijakan contoh DEMO",
            "provisional": False,
        },
    )
    command("trip.depart", {"id": first, "occurred_at": when(1)})
    for sid in (ready_pod, completed):
        command(
            "receipt.record",
            {
                "id": sid,
                "occurred_at": when(3),
                "condition": "Baik",
                "note": "Penerimaan contoh",
            },
        )
    second = make_trip(b, d, mode="final")
    command("trip.add", {"id": second, "shipment_ids": [ready_pod, completed]})
    command("trip.depart", {"id": second, "occurred_at": when(5)})
    for sid in (ready_pod, completed):
        command(
            "receipt.record",
            {
                "id": sid,
                "occurred_at": when(7),
                "condition": "Baik",
                "note": "Tiba di cabang tujuan",
            },
        )
    third = make_trip(d, d, kind="P2D", mode="final")
    command("trip.add", {"id": third, "shipment_ids": [ready_pod, completed]})
    command("trip.depart", {"id": third, "occurred_at": when(8)})
    command(
        "pod.record",
        {
            "id": completed,
            "occurred_at": when(9),
            "receiver": "Penerima Contoh",
            "exception_reason": "Contoh POD dengan bukti fisik (DEMO)",
        },
    )
    command("soa.actual", {"id": completed, "value": 90000})
    invoice = command("invoice.create", {"shipment_ids": [completed]})
    command("invoice.issue", {"id": invoice})
    command(
        "payment.record",
        {
            "id": invoice,
            "value": 100000,
            "reference": "BAYAR-DEMO-1",
            "occurred_at": when(10),
        },
    )
    command("assignment.save", {"id": ready_pod, "user_id": "demo-partner"})
    fourth = make_trip(a, b)
    command("trip.add", {"id": fourth, "shipment_ids": [fresh]})
    command(
        "field.submit",
        {
            "shipment_id": ready_pod,
            "kind": "issue",
            "reporter": "Mitra Demo",
            "contact": "000-DEMO",
            "source": "portal",
            "occurred_at": when(9),
            "note": "Contoh: penerima meminta dihubungi sebelum pengantaran.",
        },
    )
    for s in D["state"]["shipments"]:
        D["audit"].append(
            {
                "actor": "demo-admin",
                "action": "demo.seed",
                "entity_id": s["id"],
                "at": now(),
                "payload": {"reason": "Data fiktif untuk mencoba aplikasi"},
                "before": None,
                "after": None,
            }
        )
    return D


def demo_restore(raw):
    global D
    value = json.loads(raw) if raw else None
    if value and value.get("schema") == 1:
        D = value
    else:
        demo_seed()
    return json.dumps(D)


def demo_dump():
    return json.dumps(D)


def demo_user():
    u = next(
        (a for a in D["accounts"] if a["id"] == D["user_id"] and a["active"]), None
    )
    if not u:
        D["user_id"] = "demo-admin"
        u = D["accounts"][0]
    return u


def demo_switch(id):
    u = item(D["accounts"], id)
    require(u["active"], "Akun demo tidak aktif.")
    D["user_id"] = id
    return json.dumps(D)


def demo_xlsx(rows):
    """Small standards-compliant XLSX export with numeric and inline-string cells."""
    rows = rows or [{"number": "Tidak ada data"}]
    keys = list(rows[0])
    allrows = [keys] + [[r.get(k, "") for k in keys] for r in rows]
    xml = [
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
    ]
    for ri, row in enumerate(allrows, 1):
        xml.append(f'<row r="{ri}">')
        for ci, value in enumerate(row, 1):
            n = ci
            col = ""
            while n:
                n, r = divmod(n - 1, 26)
                col = chr(65 + r) + col
            ref = f"{col}{ri}"
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                xml.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                xml.append(
                    f'<c r="{ref}" t="inlineStr"><is><t xml:space="preserve">{escape(str(value))}</t></is></c>'
                )
        xml.append("</row>")
    xml.append("</sheetData></worksheet>")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        )
        z.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        )
        z.writestr(
            "xl/workbook.xml",
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="DEMO" sheetId="1" r:id="rId1"/></sheets></workbook>',
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        )
        z.writestr("xl/worksheets/sheet1.xml", "".join(xml))
    return {
        "download": base64.b64encode(stream.getvalue()).decode(),
        "mime": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "name": "manifest-DEMO.xlsx",
    }


def demo_request(path, method, raw="{}"):
    global D
    before = copy.deepcopy(D)
    try:
        u = demo_user()
        s = D["state"]
        parsed = urlparse(path)
        route = parsed.path
        filters = {k: v[0] for k, v in parse_qs(parsed.query).items()}
        body = json.loads(raw or "{}")
        if route == "/api/state":
            result = {
                "state": view_state(u, s),
                "revision": D["revision"],
                "user": u,
                "csrf": "DEMO-NOT-AUTHENTICATION",
                "permissions": sorted(permissions(u, s)),
                "accounts": D["accounts"] if u["role"] == "admin" else [],
            }
        elif route == "/api/logout":
            D["user_id"] = "demo-admin"
            result = {"ok": True}
        elif route == "/api/login":
            a = next(
                (
                    x
                    for x in D["accounts"]
                    if x["username"] == body.get("username") and x["active"]
                ),
                None,
            )
            require(a, "Pilih akun demo pada panel atas.")
            D["user_id"] = a["id"]
            result = {"user": a, "csrf": "DEMO-NOT-AUTHENTICATION"}
        elif route == "/api/command":
            action = body["action"]
            p = body["payload"]
            key = u["id"] + ":" + body["request_id"]
            digest = hashlib.sha256(
                json.dumps([action, p], sort_keys=True).encode()
            ).hexdigest()
            cached = D["requests"].get(key)
            if cached:
                require(
                    cached["digest"] == digest, "Kunci permintaan sudah digunakan.", 409
                )
                return json.dumps({"status": 200, "body": cached["response"]})
            require(
                body.get("revision") == D["revision"],
                "Data demo berubah. Muat ulang dan coba kembali.",
                409,
            )
            files = p.get("files", [])
            require(len(files) <= 5, "Maksimal lima berkas.")
            evidence = []
            for f in files:
                data = base64.b64decode(f["data"])
                require(
                    0 < len(data) <= 10 * 1024 * 1024, "Setiap berkas maksimal 10 MB."
                )
                mime = (
                    "image/png"
                    if data.startswith(b"\x89PNG\r\n\x1a\n")
                    else (
                        "image/jpeg"
                        if data.startswith(b"\xff\xd8\xff")
                        else "application/pdf" if data.startswith(b"%PDF-") else None
                    )
                )
                require(mime, "Bukti hanya JPEG, PNG, atau PDF.")
                fid = uid("FILE")
                D["evidence"][fid] = {
                    "shipment_id": p.get("shipment_id") or p.get("id"),
                    "name": f["name"],
                    "mime": mime,
                    "download": f["data"],
                }
                evidence.append(fid)
            if action == "account.save":
                require(u["role"] == "admin", "Pilih administrator demo.", 403)
                old = next((a for a in D["accounts"] if a["id"] == p.get("id")), None)
                require(
                    not any(
                        a["username"] == p["username"] and a != old
                        for a in D["accounts"]
                    ),
                    "Nama pengguna sudah dipakai.",
                )
                require(p["role"] in ROLES, "Peran tidak valid.")
                result_id = old["id"] if old else uid("USR")
                require(
                    result_id != "demo-admin"
                    or p["role"] == "admin"
                    and p.get("active", True),
                    "Administrator demo utama harus tetap aktif.",
                )
                data = {k: v for k, v in p.items() if k != "password"}
                data.update(
                    id=result_id,
                    active=bool(p.get("active", True)),
                    vendor_id=p.get("vendor_id"),
                )
                if old:
                    old.update(data)
                else:
                    D["accounts"].append(data)
            else:
                if action == "assignment.save" and p.get("user_id"):
                    assigned = item(D["accounts"], p["user_id"])
                    require(
                        assigned["active"]
                        and assigned["role"] in ("partner", "driver"),
                        "Pilih mitra/kurir demo aktif.",
                    )
                result_id = apply(u, s, action, p, evidence)
            D["revision"] += 1
            D["audit"].append(
                {
                    "actor": u["id"],
                    "action": action,
                    "entity_id": result_id,
                    "at": now(),
                    "reason": p.get("reason", ""),
                    "payload": {
                        k: v for k, v in p.items() if k not in ("files", "password")
                    },
                    "before": None,
                    "after": None,
                }
            )
            result = {"ok": True, "id": result_id, "revision": D["revision"]}
            D["requests"][key] = {"digest": digest, "response": result}
        elif route.startswith("/api/history/"):
            sid = route.rsplit("/", 1)[1]
            sh = item(s["shipments"], sid)
            require(shipment_visible(u, sh, s), "Akses simulasi cabang ditolak.", 403)
            related = {sid, *[l["trip_id"] for l in sh["legs"]]}
            result = {
                "events": [
                    a
                    for a in D["audit"]
                    if (
                        a["entity_id"] in related
                        or a["payload"].get("shipment_id") == sid
                        or sid in a["payload"].get("shipment_ids", [])
                    )
                    and (
                        finance_visible(u, sh, s)
                        or not a["action"].startswith(("soa.", "invoice.", "payment."))
                    )
                ]
            }
        elif route == "/api/audit":
            require(u["role"] == "admin", "Hanya administrator demo.", 403)
            result = {"events": list(reversed(D["audit"][-200:]))}
        elif route in ("/api/reports", "/api/reports.xlsx"):
            rows = report_rows(u, s, filters)
            result = {"rows": rows} if route.endswith("reports") else demo_xlsx(rows)
        elif route.startswith("/api/invoice/"):
            permit(u, s, "invoice")
            invoice = item(s["invoices"], route.rsplit("/", 1)[1].removesuffix(".xlsx"))
            at_branch(u, invoice["origin"])
            require(invoice["status"] == "issued", "Invoice belum terbit.")
            result = demo_xlsx(invoice["lines"])
        elif route.startswith("/api/evidence/"):
            f = D["evidence"].get(route.rsplit("/", 1)[1])
            require(f, "Bukti demo tidak tersedia.", 404)
            require(
                shipment_visible(u, item(s["shipments"], f["shipment_id"]), s),
                "Akses simulasi ditolak.",
                403,
            )
            result = f
        elif route.startswith("/print/"):
            _, _, kind, id = route.split("/")
            result = {
                "html": render_document(u, s, kind, id).replace(
                    "<body>",
                    "<body><p><strong>DATA DEMO — BUKAN DOKUMEN TRANSAKSI</strong></p>",
                )
            }
        else:
            raise Problem("Fitur demo tidak ditemukan.", 404)
        return json.dumps({"status": 200, "body": result})
    except Problem as error:
        D = before
        return json.dumps({"status": error.status, "body": {"error": error.message}})
    except (ValueError, KeyError, TypeError) as error:
        D = before
        return json.dumps(
            {
                "status": 422,
                "body": {"error": "Periksa kelengkapan dan format data demo."},
            }
        )
