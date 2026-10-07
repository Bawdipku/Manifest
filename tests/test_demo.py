import io, json, runpy, uuid
from openpyxl import load_workbook


def demo():
    module = runpy.run_path("demo/runtime.py")
    module["demo_seed"]()
    return module


def request(d, path, method="GET", body=None):
    return json.loads(d["demo_request"](path, method, json.dumps(body or {})))


def test_browser_demo_uses_domain_rules_and_local_roles():
    d = demo()
    state = request(d, "/api/state")["body"]
    assert len(state["state"]["shipments"]) == 5
    trip = next(t for t in state["state"]["trips"] if t["status"] == "draft")
    body = {
        "action": "trip.depart",
        "payload": {
            "id": trip["id"],
            "occurred_at": state["state"]["shipments"][0]["created_at"],
        },
        "revision": 0,
        "request_id": str(uuid.uuid4()),
    }
    result = request(d, "/api/command", "POST", body)
    assert result["status"] == 422 and "SOA" in result["body"]["error"]
    assert request(d, "/api/state")["body"]["revision"] == 0
    sid = state["state"]["shipments"][0]["id"]
    printed = request(d, "/print/shipment/" + sid)
    assert (
        printed["status"] == 200 and printed["body"]["html"].count('class="copy"') == 5
    )
    d["demo_switch"]("demo-partner")
    partner = request(d, "/api/state")["body"]
    assert not partner["state"]["invoices"]
    assert all("values" not in s for s in partner["state"]["shipments"])
    assert request(d, "/print/shipment/" + sid)["status"] == 403
    d["demo_seed"]()
    assert request(d, "/api/state")["body"]["user"]["id"] == "demo-admin"


def test_demo_export_and_idempotency():
    d = demo()
    body = {
        "action": "master.save",
        "payload": {"kind": "products", "name": "Test Demo"},
        "revision": 0,
        "request_id": str(uuid.uuid4()),
    }
    first = request(d, "/api/command", "POST", body)
    assert first["status"] == 200
    assert request(d, "/api/command", "POST", body) == first
    rows = [{"number": "=not-a-formula", "value": 12500}]
    out = d["demo_xlsx"](rows)
    import base64

    book = load_workbook(io.BytesIO(base64.b64decode(out["download"])))
    sheet = book.active
    assert sheet["A2"].value == "=not-a-formula" and sheet["A2"].data_type == "s"
    assert sheet["B2"].value == 12500
    saved = d["demo_dump"]()
    d["demo_seed"]()
    d["demo_restore"](saved)
    assert request(d, "/api/state")["body"]["revision"] == 1
