import base64, json, uuid
from datetime import datetime, timedelta, timezone
import pytest
from werkzeug.security import generate_password_hash
from backend.app import create_app

PASSWORD = "Testing-only-password-42!"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("COOKIE_SECURE", "false")
    app = create_app(tmp_path / "test.sqlite3", testing=True)
    with app.connect() as c:
        c.execute(
            "INSERT INTO users VALUES(?,?,?,?,?,?,?,?)",
            (
                "root",
                "admin",
                "Admin",
                generate_password_hash(PASSWORD),
                "admin",
                "[]",
                None,
                1,
            ),
        )
    client = app.test_client()
    assert (
        client.post(
            "/api/login", json={"username": "admin", "password": PASSWORD}
        ).status_code
        == 200
    )
    return app, client


def state(c):
    r = c.get("/api/state")
    assert r.status_code == 200, r.json
    return r.json


def cmd(c, action, payload, expected=200, revision=None, key=None):
    s = state(c)
    r = c.post(
        "/api/command",
        headers={"X-CSRF-Token": s["csrf"]},
        json={
            "action": action,
            "payload": payload,
            "request_id": key or str(uuid.uuid4()),
            "revision": s["revision"] if revision is None else revision,
        },
    )
    assert r.status_code == expected, r.json
    return r.json.get("id") if expected == 200 else r


def t(hours=0):
    return (
        datetime.now(timezone.utc) - timedelta(days=2) + timedelta(hours=hours)
    ).isoformat()


def login(app, name):
    c = app.test_client()
    r = c.post("/api/login", json={"username": name, "password": PASSWORD})
    assert r.status_code == 200, r.json
    return c


def setup(c):
    a = cmd(
        c,
        "master.save",
        {
            "kind": "branches",
            "name": "Asal",
            "prefix": "PKU",
            "office_code": "PKU",
            "city_code": "PKU",
        },
    )
    b = cmd(
        c,
        "master.save",
        {
            "kind": "branches",
            "name": "Hub",
            "prefix": "HUB",
            "office_code": "HUB",
            "city_code": "HUB",
        },
    )
    d = cmd(
        c,
        "master.save",
        {
            "kind": "branches",
            "name": "Tujuan",
            "prefix": "BTM",
            "office_code": "BTM",
            "city_code": "BTM",
        },
    )
    customer = cmd(
        c,
        "master.save",
        {
            "kind": "customers",
            "name": "PT DATA DEMO",
            "address": "Alamat demo",
            "contact": "000",
        },
    )
    vendor = cmd(c, "master.save", {"kind": "vendors", "name": "Vendor Demo"})
    return a, b, d, customer, vendor


def shipment(c, a, d, customer):
    return cmd(
        c,
        "shipment.save",
        {
            "origin": a,
            "final_branch": d,
            "destination": "Batam",
            "customer_id": customer,
            "receiver": "Penerima demo",
            "address": "Alamat contoh",
            "contact": "000",
            "packages": 2,
            "weight": 10,
            "ship_date": "2026-10-01",
            "credit": 50000,
            "cash": 10000,
            "collect": 0,
            "forwarding": 1000,
            "register": True,
        },
    )


def trip(c, a, b, mode="transit", kind="P2P", vendor=None):
    return cmd(
        c,
        "trip.create",
        {
            "origin": a,
            "destination": b,
            "type": kind,
            "mode": mode,
            "executor": "vendor" if vendor else "internal",
            "vendor_id": vendor,
            "vendor_reference": "V-001",
            "driver": "Driver Demo",
            "vehicle": "BM DEMO",
            "planned_date": "2026-10-01",
        },
    )


def receive(c, s, h=1):
    return cmd(
        c,
        "receipt.record",
        {"id": s, "occurred_at": t(h), "condition": "Baik", "note": "Tes"},
    )


def test_three_stage_partial_receipt_finance_documents_and_print(env):
    app, c = env
    a, b, d, customer, vendor = setup(c)
    s1 = shipment(c, a, d, customer)
    s2 = shipment(c, a, d, customer)
    first = trip(c, a, b)
    cmd(c, "trip.add", {"id": first, "shipment_ids": [s1, s2]})
    cmd(c, "trip.depart", {"id": first, "occurred_at": t()}, 422)
    cmd(
        c,
        "soa.confirm",
        {
            "trip_id": first,
            "destination": "Batam",
            "amounts": {s1: 15000, s2: 17000},
            "policy": "Aturan demo",
            "provisional": False,
        },
    )
    snapshot = next(s for s in state(c)["state"]["shipments"] if s["id"] == s1)[
        "soa"
    ].copy()
    cmd(c, "trip.depart", {"id": first, "occurred_at": t()})
    cmd(
        c, "trip.remove", {"id": first, "shipment_id": s1, "reason": "Tidak boleh"}, 422
    )
    cmd(
        c,
        "pod.record",
        {"id": s1, "occurred_at": t(1), "receiver": "A", "exception_reason": "Tes"},
        422,
    )
    receive(c, s1, 1)
    second = trip(c, b, d, mode="final")
    cmd(c, "trip.add", {"id": second, "shipment_ids": [s2]}, 422)
    cmd(c, "trip.add", {"id": second, "shipment_ids": [s1]})
    another = trip(c, b, d, mode="final")
    cmd(c, "trip.add", {"id": another, "shipment_ids": [s1]}, 422)
    cmd(c, "trip.depart", {"id": second, "occurred_at": t(0.5)}, 422)
    cmd(c, "trip.depart", {"id": second, "occurred_at": t(2)})
    receive(c, s1, 3)
    third = trip(c, d, d, mode="final", kind="P2D", vendor=vendor)
    cmd(c, "trip.add", {"id": third, "shipment_ids": [s1]})
    cmd(c, "trip.depart", {"id": third, "occurred_at": t(4)})
    cmd(
        c,
        "pod.record",
        {"id": s1, "occurred_at": t(5), "receiver": "A", "exception_reason": "Tes"},
        422,
    )
    cmd(c, "trip.handover", {"id": third, "occurred_at": t(4.5), "reference": "VH-1"})
    cmd(
        c,
        "pod.record",
        {"id": s1, "occurred_at": t(4.2), "receiver": "A", "exception_reason": "Tes"},
        422,
    )
    # Credit invoicing does not require POD.
    invoice = cmd(c, "invoice.create", {"shipment_ids": [s1]})
    cmd(c, "invoice.create", {"shipment_ids": [s1]}, 422)
    cmd(c, "invoice.issue", {"id": invoice})
    cmd(
        c,
        "master.save",
        {"kind": "customers", "id": customer, "name": "Master renamed"},
    )
    assert (
        state(c)["state"]["invoices"][0]["customer_snapshot"]["name"] == "PT DATA DEMO"
    )
    cmd(
        c,
        "payment.record",
        {"id": invoice, "value": 60000, "reference": "A", "occurred_at": t(5)},
        422,
    )
    cmd(
        c,
        "payment.record",
        {"id": invoice, "value": 20000, "reference": "A", "occurred_at": t(5)},
    )
    cmd(
        c,
        "payment.record",
        {"id": invoice, "value": 1000, "reference": "A", "occurred_at": t(5)},
        422,
    )
    pay = state(c)["state"]["invoices"][0]["payments"][0]
    cmd(
        c,
        "payment.reverse",
        {"id": invoice, "payment_id": pay["id"], "reason": "Koreksi"},
    )
    assert state(c)["state"]["invoices"][0]["payments"][0]["reversed"]
    cmd(
        c,
        "pod.record",
        {
            "id": s1,
            "occurred_at": t(5),
            "receiver": "Penerima",
            "exception_reason": "Bukti fisik disimpan di cabang",
        },
    )
    cmd(c, "soa.actual", {"id": s1, "value": 18000})
    cmd(c, "soa.resolve", {"id": s1, "reason": "Selisih disetujui"})
    ret = cmd(c, "return.create", {"shipment_ids": [s1], "reference": "RET-1"})
    cmd(c, "return.receive", {"id": ret, "note": "Fisik lengkap"})
    final = next(s for s in state(c)["state"]["shipments"] if s["id"] == s1)
    assert len(final["legs"]) == 3
    assert final["soa"] == snapshot
    assert final["first_departed_at"] == state(c)["state"]["trips"][0]["departed_at"]
    assert final["document_status"] == "received_origin"
    assert s1 in state(c)["state"]["trips"][0]["shipment_ids"]
    assert final["sender"]["name"] == "PT DATA DEMO"
    assert final["actual_soa"]["status"] == "resolved"
    report = c.get("/api/reports?view=sales").json["rows"]
    assert len(report) == 2
    assert sum(x["revenue"] for x in report) == 120000
    document = c.get("/print/shipment/" + s1)
    assert document.status_code == 200
    html = document.text
    assert html.count('class="copy"') == 5
    assert "Barcode Code 128" in html
    assert "30 Hari" in html
    assert "1.000.000" in html
    assert c.get("/print/trip/" + first).status_code == 200
    assert c.get("/print/invoice/" + invoice).status_code == 200
    assert c.get("/api/reports.xlsx").status_code == 200


def test_access_reassignment_evidence_and_report_approval(env):
    app, c = env
    a, b, d, customer, vendor = setup(c)
    sid = shipment(c, a, d, customer)
    tid = trip(c, a, b)
    cmd(c, "trip.add", {"id": tid, "shipment_ids": [sid]})
    cmd(
        c,
        "soa.confirm",
        {
            "trip_id": tid,
            "destination": "Batam",
            "amounts": {sid: 10},
            "policy": "Demo",
        },
    )
    cmd(c, "trip.depart", {"id": tid, "occurred_at": t()})
    users = {}
    for name, role, branches in [
        ("oldpartner", "partner", [a]),
        ("newpartner", "partner", [a]),
        ("hubfinance", "finance", [b]),
        ("hubstaff", "warehouse", [b]),
        ("readonly", "auditor", [a]),
    ]:
        users[name] = cmd(
            c,
            "account.save",
            {
                "username": name,
                "name": name,
                "password": PASSWORD,
                "role": role,
                "branches": branches,
                "active": True,
            },
        )
    cmd(c, "assignment.save", {"id": sid, "user_id": users["oldpartner"]})
    old = login(app, "oldpartner")
    new = login(app, "newpartner")
    assert len(state(old)["state"]["shipments"]) == 1
    assert not state(new)["state"]["shipments"]
    assert "values" not in state(old)["state"]["shipments"][0]
    assert "customers" not in state(old)["state"]["masters"]
    image = {
        "name": "proof.png",
        "data": base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 20).decode(),
    }
    rid = cmd(
        old,
        "field.submit",
        {
            "shipment_id": sid,
            "kind": "arrival",
            "occurred_at": t(1),
            "reporter": "Mitra",
            "contact": "000",
            "source": "portal",
            "condition": "Baik",
            "files": [image],
        },
    )
    assert (
        next(x for x in state(c)["state"]["shipments"] if x["id"] == sid)[
            "operational_status"
        ]
        == "in_transit"
    )
    evid = state(old)["state"]["field_reports"][0]["evidence_ids"][0]
    assert old.get("/api/evidence/" + evid).status_code == 200
    cmd(c, "assignment.save", {"id": sid, "user_id": users["newpartner"]})
    assert old.get("/api/evidence/" + evid).status_code == 403
    assert old.get("/api/history/" + sid).status_code == 403
    assert state(old)["state"]["shipments"] == []
    assert new.get("/api/evidence/" + evid).status_code == 200
    cmd(new, "field.review", {"id": rid, "decision": "approved", "reason": "No"}, 403)
    cmd(
        c, "field.review", {"id": rid, "decision": "approved", "reason": "Bukti sesuai"}
    )
    hub = login(app, "hubfinance")
    hv = state(hub)["state"]
    assert len(hv["shipments"]) == 1 and "values" not in hv["shipments"][0]
    assert not hv["soa_groups"]
    assert hub.get("/print/shipment/" + sid).status_code == 403
    assert hub.get("/api/reports?view=sales").json["rows"] == []
    cmd(hub, "soa.actual", {"id": sid, "value": 1}, 403)
    reader = login(app, "readonly")
    cmd(reader, "shipment.cancel", {"id": sid, "reason": "No"}, 403)
    # Approving a report cannot manufacture a transit POD, even with evidence.
    rid = cmd(
        new,
        "field.submit",
        {
            "shipment_id": sid,
            "kind": "pod",
            "occurred_at": t(2),
            "reporter": "Mitra",
            "contact": "000",
            "source": "portal",
            "receiver": "Penerima",
            "files": [image],
        },
    )
    cmd(c, "field.review", {"id": rid, "decision": "approved", "reason": "No"}, 422)


def test_idempotency_revision_rollback_and_csrf(env):
    app, c = env
    a, b, d, customer, vendor = setup(c)
    rev = state(c)["revision"]
    key = str(uuid.uuid4())
    p = {"kind": "products", "name": "Demo"}
    one = cmd(c, "master.save", p, revision=rev, key=key)
    two = cmd(c, "master.save", p, revision=rev, key=key)
    assert one == two
    cmd(
        c,
        "master.save",
        {"kind": "products", "name": "Other"},
        expected=409,
        revision=rev,
        key=key,
    )
    cmd(
        c,
        "master.save",
        {"kind": "products", "name": "Other"},
        expected=409,
        revision=rev,
    )
    r = c.post(
        "/api/command",
        json={
            "action": "master.save",
            "payload": p,
            "revision": state(c)["revision"],
            "request_id": str(uuid.uuid4()),
        },
    )
    assert r.status_code == 403
    before = state(c)["revision"]
    s1 = shipment(c, a, d, customer)
    tid = trip(c, a, b)
    cmd(c, "trip.add", {"id": tid, "shipment_ids": [s1, "missing"]}, 404)
    assert not next(x for x in state(c)["state"]["trips"] if x["id"] == tid)[
        "shipment_ids"
    ]
    cmd(c, "trip.add", {"id": tid, "shipment_ids": [s1, s1]}, 422)
    anon = app.test_client()
    assert anon.get("/api/state").status_code == 401
    assert anon.get("/print/shipment/" + s1).status_code == 401


def test_provisional_cancellation_and_document_boundaries(env):
    app, c = env
    a, b, d, customer, vendor = setup(c)
    sid = shipment(c, a, a, customer)
    tid = trip(c, a, a, "final", "P2D")
    cmd(c, "trip.add", {"id": tid, "shipment_ids": [sid]})
    cmd(
        c,
        "soa.confirm",
        {
            "trip_id": tid,
            "destination": "Batam",
            "amounts": {sid: 100},
            "policy": "Provisional",
            "provisional": True,
        },
    )
    cmd(c, "trip.depart", {"id": tid, "occurred_at": t()})
    cmd(
        c,
        "pod.record",
        {"id": sid, "occurred_at": t(1), "receiver": "A", "exception_reason": "Fisik"},
    )
    cmd(c, "soa.actual", {"id": sid, "value": 100})
    cmd(c, "soa.resolve", {"id": sid, "reason": "No"}, 422)
    cmd(c, "soa.approve_policy", {"id": sid, "reason": "Aturan disetujui"})
    cmd(c, "soa.resolve", {"id": sid, "reason": "Sesuai"})
    assert state(c)["state"]["shipments"][0]["document_status"] == "waiting_return"
    cancelled = shipment(c, a, d, customer)
    cmd(c, "shipment.cancel", {"id": cancelled, "reason": "Salah input"})
    assert len(c.get("/api/reports?view=sales").json["rows"]) == 1
    assert len(c.get("/api/reports?view=cancelled").json["rows"]) == 1


def test_partner_pod_approval_pending_and_origin_document_scope(env):
    app, c = env
    a, b, d, customer, vendor = setup(c)
    sid = shipment(c, a, a, customer)
    tid = trip(c, a, a, "final", "P2D")
    cmd(c, "trip.add", {"id": tid, "shipment_ids": [sid]})
    cmd(
        c,
        "soa.confirm",
        {
            "trip_id": tid,
            "destination": "Batam",
            "amounts": {sid: 100},
            "policy": "Valid",
        },
    )
    cmd(c, "trip.depart", {"id": tid, "occurred_at": t()})
    partnerid = cmd(
        c,
        "account.save",
        {
            "username": "partner",
            "name": "Partner",
            "role": "partner",
            "branches": [a],
            "password": PASSWORD,
        },
    )
    cmd(c, "assignment.save", {"id": sid, "user_id": partnerid})
    partner = login(app, "partner")
    p = {
        "shipment_id": sid,
        "kind": "pod",
        "occurred_at": t(1),
        "reporter": "Mitra",
        "contact": "000",
        "source": "portal",
        "receiver": "Penerima",
    }
    rid = cmd(partner, "field.submit", p)
    cmd(
        c,
        "field.review",
        {"id": rid, "decision": "approved", "reason": "No evidence"},
        422,
    )
    cmd(
        c, "field.review", {"id": rid, "decision": "rejected", "reason": "Unggah bukti"}
    )
    p["files"] = [
        {"name": "proof.pdf", "data": base64.b64encode(b"%PDF-1.4\nDemo").decode()}
    ]
    rid = cmd(partner, "field.submit", p)
    cmd(
        c,
        "pod.record",
        {"id": sid, "occurred_at": t(1), "receiver": "A", "exception_reason": "No"},
        422,
    )
    cmd(
        c,
        "field.review",
        {"id": rid, "decision": "approved", "reason": "Bukti terverifikasi"},
    )
    final = state(c)["state"]["shipments"][0]
    assert final["pod"]["receiver"] == "Penerima"
    assert final["actual_soa"] is None
    assert final["document_status"] == "waiting_return"
    ret = cmd(c, "return.create", {"shipment_ids": [sid], "reference": "R-2"})
    uid = cmd(
        c,
        "account.save",
        {
            "username": "wrongbranch",
            "name": "Warehouse",
            "role": "warehouse",
            "branches": [b],
            "password": PASSWORD,
        },
    )
    other = login(app, "wrongbranch")
    cmd(other, "return.receive", {"id": ret, "note": "Tidak boleh"}, 403)
    assert other.get("/print/trip/" + tid).status_code == 403
    assert other.get("/api/history/" + sid).status_code == 403
    invoice = cmd(c, "invoice.create", {"shipment_ids": [sid]})
    cmd(c, "invoice.issue", {"id": invoice})
    cmd(
        c,
        "payment.record",
        {"id": invoice, "reference": "P-1", "value": 50000, "occurred_at": t(2)},
    )
    r = c.get("/api/reports?view=finance").json["rows"]
    assert len(r) == 1 and r[0]["balance"] == 0 and r[0]["paid"] == 50000
    assert "revenue" not in r[0]
    assert partner.get("/api/reports?view=finance").status_code == 403
    assert partner.get("/api/invoice/" + invoice + ".xlsx").status_code == 403
    # Disablement invalidates old sessions immediately.
    cmd(
        c,
        "account.save",
        {
            "id": partnerid,
            "username": "partner",
            "name": "Partner",
            "role": "partner",
            "branches": [a],
            "active": False,
        },
    )
    assert partner.get("/api/state").status_code == 401


def test_bulk_limit_and_report_blocks_forwarding(env):
    app, c = env
    a, b, d, customer, vendor = setup(c)
    sid = shipment(c, a, d, customer)
    tid = trip(c, a, b)
    cmd(c, "trip.add", {"id": tid, "shipment_ids": [str(i) for i in range(201)]}, 422)
    cmd(c, "trip.add", {"id": tid, "shipment_ids": [sid]})
    cmd(
        c,
        "soa.confirm",
        {
            "trip_id": tid,
            "destination": "Batam",
            "amounts": {sid: 10},
            "policy": "Demo",
        },
    )
    cmd(c, "trip.depart", {"id": tid, "occurred_at": t()})
    receive(c, sid, 1)
    rid = cmd(
        c,
        "field.submit",
        {
            "shipment_id": sid,
            "kind": "issue",
            "occurred_at": t(1),
            "reporter": "Admin via phone",
            "contact": "000",
            "source": "phone",
            "note": "Periksa kemasan",
        },
    )
    nexttrip = trip(c, b, d, "final")
    cmd(c, "trip.add", {"id": nexttrip, "shipment_ids": [sid]}, 422)
    cmd(
        c,
        "field.review",
        {"id": rid, "decision": "approved", "reason": "Kendala tercatat"},
    )
    cmd(c, "field.resolve", {"id": rid, "reason": "Kemasan diperbaiki"})
    cmd(c, "trip.add", {"id": nexttrip, "shipment_ids": [sid]})
    cmd(c, "trip.remove", {"id": nexttrip, "shipment_id": sid, "reason": "Ubah jadwal"})
    s = state(c)["state"]["shipments"][0]
    assert len(s["legs"]) == 1 and s["legs"][0]["received_at"]
    assert s["operational_status"] == "arrived"


def test_report_archive_timezone_and_backup(env, tmp_path):
    import os, subprocess, sys, sqlite3

    app, c = env
    a, b, d, customer, vendor = setup(c)
    sid = shipment(c, a, d, customer)
    with app.connect() as db:
        row = db.execute("SELECT data FROM state").fetchone()
        s = json.loads(row["data"])
        s["shipments"][0]["registered_at"] = "2026-10-01T18:30:00+00:00"
        db.execute("UPDATE state SET data=?", (json.dumps(s),))
    assert len(c.get("/api/reports?from=2026-10-02&to=2026-10-02").json["rows"]) == 1
    assert not c.get("/api/reports?from=2026-10-01&to=2026-10-01").json["rows"]
    archive = cmd(
        c, "report.archive", {"view": "sales", "from": "2026-10-02", "to": "2026-10-02"}
    )
    cmd(c, "shipment.cancel", {"id": sid, "reason": "Koreksi"})
    assert len(state(c)["state"]["archives"][0]["rows"]) == 1
    assert c.get("/api/audit").status_code == 200
    target = tmp_path / "backup.sqlite3"
    subprocess.run(
        [sys.executable, "-m", "backend.backup", str(target)],
        env={**os.environ, "DATABASE_PATH": str(app.dbfile)},
        check=True,
        capture_output=True,
    )
    with sqlite3.connect(target) as db:
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("SELECT COUNT(*) FROM audit").fetchone()[0] > 0
