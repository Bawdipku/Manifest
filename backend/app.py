import base64, copy, hashlib, hmac, io, json, os, re, secrets, sqlite3, time
from datetime import datetime, timezone
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, send_file, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.middleware.proxy_fix import ProxyFix
from .domain import *

ROOT = Path(__file__).resolve().parent.parent


def create_app(db_path=None, testing=False):
    app = Flask(__name__, static_folder=None)
    app.config.update(MAX_CONTENT_LENGTH=71 * 1024 * 1024, TESTING=testing)
    if os.environ.get("TRUST_PROXY") == "1":
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0)
    dbfile = Path(
        db_path or os.environ.get("DATABASE_PATH", ROOT / "data/manifest.sqlite3")
    )
    dbfile.parent.mkdir(parents=True, exist_ok=True)

    def connect():
        c = sqlite3.connect(dbfile, timeout=20)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA foreign_keys=ON")
        return c

    with connect() as c:
        c.executescript(
            """PRAGMA journal_mode=WAL;
   CREATE TABLE IF NOT EXISTS state(id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL, data TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,name TEXT NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL,branches TEXT NOT NULL,vendor_id TEXT,active INTEGER NOT NULL DEFAULT 1);
   CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),csrf TEXT NOT NULL,expires INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS requests(user_id TEXT,request_id TEXT,digest TEXT,response TEXT,PRIMARY KEY(user_id,request_id));
   CREATE TABLE IF NOT EXISTS evidence(id TEXT PRIMARY KEY,shipment_id TEXT NOT NULL,name TEXT NOT NULL,mime TEXT NOT NULL,data BLOB NOT NULL,actor TEXT NOT NULL,created_at TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,actor TEXT,action TEXT,entity_id TEXT,at TEXT,payload TEXT,before_json TEXT,after_json TEXT);
   CREATE TABLE IF NOT EXISTS login_attempts(ip TEXT PRIMARY KEY,count INTEGER,until INTEGER);
  """
        )
        c.execute(
            "INSERT OR IGNORE INTO state VALUES(1,0,?)", (json.dumps(init_state()),)
        )

    def public_user(row):
        return {
            k: json.loads(row[k]) if k == "branches" else row[k]
            for k in (
                "id",
                "username",
                "name",
                "role",
                "branches",
                "vendor_id",
                "active",
            )
        }

    def load(c):
        row = c.execute("SELECT * FROM state WHERE id=1").fetchone()
        return row["revision"], json.loads(row["data"])

    def authenticate(c):
        token = request.cookies.get("manifest_session", "")
        row = c.execute(
            "SELECT s.csrf,s.expires,u.* FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?",
            (hashlib.sha256(token.encode()).hexdigest(),),
        ).fetchone()
        require(
            row is not None and row["expires"] > time.time() and row["active"],
            "Silakan masuk kembali.",
            401,
        )
        u = public_user(row)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            require(
                hmac.compare_digest(
                    request.headers.get("X-CSRF-Token", ""), row["csrf"]
                ),
                "Token keamanan tidak valid.",
                403,
            )
        return u, row["csrf"]

    @app.before_request
    def guard():
        if request.path.startswith("/api/") or request.path.startswith("/print/"):
            g.c = connect()
            if request.path != "/api/login":
                g.user, g.csrf = authenticate(g.c)
            if request.method not in ("GET", "HEAD", "OPTIONS"):
                origin = request.headers.get("Origin")
                expected = os.environ.get("APP_ORIGIN")
                if origin:
                    require(
                        origin == (expected or request.host_url.rstrip("/")),
                        "Asal permintaan ditolak.",
                        403,
                    )

    @app.teardown_request
    def close_db(error):
        if hasattr(g, "c"):
            g.c.close()

    @app.after_request
    def headers(res):
        res.headers["X-Content-Type-Options"] = "nosniff"
        res.headers["X-Frame-Options"] = "DENY"
        res.headers["Referrer-Policy"] = "same-origin"
        res.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'self'"
        )
        if request.path.startswith(("/api/", "/print/")):
            res.headers["Cache-Control"] = "no-store"
        return res

    @app.errorhandler(Problem)
    def handle(e):
        return jsonify(error=e.message), e.status

    @app.errorhandler(413)
    def too_big(e):
        return (
            jsonify(error="Ukuran unggahan terlalu besar; maksimal 5 berkas × 10 MB."),
            413,
        )

    @app.errorhandler(ValueError)
    @app.errorhandler(TypeError)
    def invalid(e):
        return jsonify(error="Format nilai tidak valid."), 422

    @app.get("/health")
    def health():
        with connect() as c:
            c.execute("SELECT revision FROM state WHERE id=1").fetchone()
        return jsonify(status="ok")

    @app.post("/api/login")
    def login():
        p = request.get_json()
        ip = request.remote_addr
        row = g.c.execute("SELECT * FROM login_attempts WHERE ip=?", (ip,)).fetchone()
        require(
            not row or row["until"] < time.time() or row["count"] < 10,
            "Terlalu banyak percobaan. Tunggu 15 menit.",
            429,
        )
        u = g.c.execute(
            "SELECT * FROM users WHERE username=?",
            (str(p.get("username", "")).lower(),),
        ).fetchone()
        valid = check_password_hash(
            u["password"] if u else generate_password_hash("invalid-placeholder"),
            str(p.get("password", "")),
        )
        if not u or not u["active"] or not valid:
            with g.c:
                g.c.execute(
                    "INSERT INTO login_attempts VALUES(?,1,?) ON CONFLICT(ip) DO UPDATE SET count=CASE WHEN until<? THEN 1 ELSE count+1 END,until=?",
                    (
                        ip,
                        int(time.time() + 900),
                        int(time.time()),
                        int(time.time() + 900),
                    ),
                )
            raise Problem("Nama pengguna atau kata sandi salah.", 401)
        token = secrets.token_urlsafe(40)
        csrf = secrets.token_urlsafe(32)
        with g.c:
            g.c.execute("DELETE FROM login_attempts WHERE ip=?", (ip,))
            g.c.execute("DELETE FROM sessions WHERE expires<?", (int(time.time()),))
            g.c.execute(
                "INSERT INTO sessions VALUES(?,?,?,?)",
                (
                    hashlib.sha256(token.encode()).hexdigest(),
                    u["id"],
                    csrf,
                    int(time.time() + 43200),
                ),
            )
        res = jsonify(user=public_user(u), csrf=csrf)
        res.set_cookie(
            "manifest_session",
            token,
            httponly=True,
            secure=os.environ.get("COOKIE_SECURE", "true") == "true",
            samesite="Strict",
            max_age=43200,
        )
        return res

    @app.post("/api/logout")
    def logout():
        with g.c:
            g.c.execute(
                "DELETE FROM sessions WHERE token_hash=?",
                (
                    hashlib.sha256(
                        request.cookies.get("manifest_session", "").encode()
                    ).hexdigest(),
                ),
            )
        res = jsonify(ok=True)
        res.delete_cookie("manifest_session")
        return res

    @app.get("/api/state")
    def state():
        rev, s = load(g.c)
        v = view_state(g.user, s)
        accounts = []
        if g.user["role"] == "admin":
            accounts = [
                public_user(x) for x in g.c.execute("SELECT * FROM users ORDER BY name")
            ]
        return jsonify(
            revision=rev,
            state=v,
            user=g.user,
            csrf=g.csrf,
            permissions=sorted(permissions(g.user, s)),
            accounts=accounts,
        )

    def save_account(c, u, s, p):
        permit(u, s, "accounts")
        require(u["role"] == "admin", "Hanya administrator.", 403)
        username = text(p, "username").lower()
        require(
            re.fullmatch("[a-z0-9_.-]{3,60}", username),
            "Nama pengguna harus 3–60 huruf/angka.",
        )
        role = text(p, "role")
        require(role in ROLES, "Peran tidak valid.")
        branches = p.get("branches", [])
        require(isinstance(branches, list), "Cakupan harus daftar cabang.")
        for b in branches:
            item(s["masters"]["branches"], b)
        if role != "admin":
            require(branches, "Pilih cabang akun.")
        if p.get("vendor_id"):
            item(s["masters"]["vendors"], p["vendor_id"])
        old = c.execute("SELECT * FROM users WHERE id=?", (p.get("id"),)).fetchone()
        password = str(p.get("password", ""))
        require(old or len(password) >= 12, "Kata sandi minimal 12 karakter.")
        require(not password or len(password) >= 12, "Kata sandi minimal 12 karakter.")
        id = old["id"] if old else uid("USR")
        active_ = bool(p.get("active", True))
        require(
            id != u["id"] or active_ and role == "admin",
            "Administrator tidak dapat menonaktifkan atau menurunkan perannya sendiri.",
        )
        try:
            c.execute(
                "INSERT INTO users VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET username=excluded.username,name=excluded.name,password=excluded.password,role=excluded.role,branches=excluded.branches,vendor_id=excluded.vendor_id,active=excluded.active",
                (
                    id,
                    username,
                    text(p, "name"),
                    generate_password_hash(password) if password else old["password"],
                    role,
                    json.dumps(branches),
                    p.get("vendor_id"),
                    active_,
                ),
            )
        except sqlite3.IntegrityError:
            raise Problem("Nama pengguna sudah digunakan.")
        if old:
            c.execute("DELETE FROM sessions WHERE user_id=?", (id,))
        return id

    def entity(s, id):
        for rows in s.values():
            if isinstance(rows, list):
                for r in rows:
                    if isinstance(r, dict) and r.get("id") == id:
                        return r
        for rows in s["masters"].values():
            for r in rows:
                if r.get("id") == id:
                    return r
        return None

    @app.post("/api/command")
    def command():
        body = request.get_json()
        action = text(body, "action")
        p = body.get("payload", {})
        require(isinstance(p, dict), "Payload tidak valid.")
        reqid = text(body, "request_id")
        require(len(reqid) <= 100, "Kunci permintaan terlalu panjang.")
        digest = hashlib.sha256(
            json.dumps({"action": action, "payload": p}, sort_keys=True).encode()
        ).hexdigest()
        c = g.c
        try:
            c.execute("BEGIN IMMEDIATE")
            u, _ = authenticate(c)
            cached = c.execute(
                "SELECT * FROM requests WHERE user_id=? AND request_id=?",
                (u["id"], reqid),
            ).fetchone()
            if cached:
                require(
                    cached["digest"] == digest,
                    "Kunci permintaan telah digunakan untuk data berbeda.",
                    409,
                )
                c.rollback()
                return jsonify(json.loads(cached["response"]))
            revision, s = load(c)
            require(
                body.get("revision") == revision,
                "Data berubah. Muat ulang sebelum menyimpan.",
                409,
            )
            before = copy.deepcopy(s)
            evidence_ids = []
            files = p.get("files", [])
            require(
                isinstance(files, list) and len(files) <= 5,
                "Maksimal lima berkas per laporan.",
            )
            require(
                not files or action in ("pod.record", "field.submit"),
                "Unggahan tidak didukung pada tindakan ini.",
            )
            for f in files:
                try:
                    data = base64.b64decode(f["data"], validate=True)
                except Exception:
                    raise Problem("Berkas tidak valid.")
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
                require(mime is not None, "Bukti hanya JPEG, PNG, atau PDF.")
                sid = p.get("shipment_id") or p.get("id")
                s1 = item(s["shipments"], sid)
                require(shipment_visible(u, s1, s), "Akses resi ditolak.", 403)
                fid = uid("FILE")
                c.execute(
                    "INSERT INTO evidence VALUES(?,?,?,?,?,?,?)",
                    (
                        fid,
                        sid,
                        str(f.get("name", "bukti"))[:200],
                        mime,
                        data,
                        u["id"],
                        now(),
                    ),
                )
                evidence_ids.append(fid)
            if action == "account.save":
                result = save_account(c, u, s, p)
            else:
                if action == "assignment.save" and p.get("user_id"):
                    account = c.execute(
                        "SELECT * FROM users WHERE id=? AND active=1", (p["user_id"],)
                    ).fetchone()
                    require(
                        account and account["role"] in ("partner", "driver"),
                        "Pilih akun kurir/mitra aktif.",
                    )
                result = apply(u, s, action, p, evidence_ids)
            c.execute(
                "UPDATE state SET revision=?,data=? WHERE id=1",
                (revision + 1, json.dumps(s)),
            )
            safe = {k: v for k, v in p.items() if k not in ("password", "files")}
            c.execute(
                "INSERT INTO audit(actor,action,entity_id,at,payload,before_json,after_json) VALUES(?,?,?,?,?,?,?)",
                (
                    u["id"],
                    action,
                    result,
                    now(),
                    json.dumps(safe),
                    json.dumps(entity(before, result)),
                    json.dumps(entity(s, result)),
                ),
            )
            response = {"ok": True, "id": result, "revision": revision + 1}
            c.execute(
                "INSERT INTO requests VALUES(?,?,?,?)",
                (u["id"], reqid, digest, json.dumps(response)),
            )
            c.commit()
            return jsonify(response)
        except Exception:
            c.rollback()
            raise

    @app.get("/api/evidence/<id>")
    def evidence(id):
        _, s = load(g.c)
        f = g.c.execute("SELECT * FROM evidence WHERE id=?", (id,)).fetchone()
        require(f is not None, "Bukti tidak ditemukan.", 404)
        ship = item(s["shipments"], f["shipment_id"])
        require(shipment_visible(g.user, ship, s), "Akses bukti ditolak.", 403)
        return send_file(
            io.BytesIO(f["data"]),
            mimetype=f["mime"],
            as_attachment=True,
            download_name=f["name"],
        )

    @app.get("/api/audit")
    def audit():
        require(g.user["role"] == "admin", "Riwayat audit hanya administrator.", 403)
        return jsonify(
            events=[
                {
                    "actor": r["actor"],
                    "action": r["action"],
                    "entity_id": r["entity_id"],
                    "at": r["at"],
                    "payload": json.loads(r["payload"]),
                    "before": json.loads(r["before_json"]),
                    "after": json.loads(r["after_json"]),
                }
                for r in g.c.execute("SELECT * FROM audit ORDER BY id DESC LIMIT 200")
            ]
        )

    @app.get("/api/history/<id>")
    def history(id):
        _, s = load(g.c)
        ship = item(s["shipments"], id)
        require(shipment_visible(g.user, ship, s), "Akses ditolak.", 403)
        related = {id, *[l["trip_id"] for l in ship["legs"]]}
        events = []
        for r in g.c.execute("SELECT * FROM audit ORDER BY id DESC"):
            p = json.loads(r["payload"])
            hit = (
                r["entity_id"] in related
                or p.get("shipment_id") == id
                or id in p.get("shipment_ids", [])
            )
            if not hit:
                continue
            if r["action"].startswith(
                ("soa.", "invoice.", "payment.")
            ) and not finance_visible(g.user, ship, s):
                continue
            ev = {
                "action": r["action"],
                "actor": r["actor"],
                "at": r["at"],
                "reason": p.get("reason", ""),
            }
            if not external(g.user) and finance_visible(g.user, ship, s):
                ev.update(
                    payload=p,
                    before=json.loads(r["before_json"]),
                    after=json.loads(r["after_json"]),
                )
            events.append(ev)
        return jsonify(events=events)

    @app.get("/api/reports")
    def reports():
        _, s = load(g.c)
        return jsonify(rows=report_rows(g.user, s, request.args))

    @app.get("/api/reports.xlsx")
    def excel():
        from openpyxl import Workbook

        _, s = load(g.c)
        rows = report_rows(g.user, s, request.args)
        book = Workbook()
        ws = book.active
        ws.title = "Laporan"
        keys = list(rows[0]) if rows else ["number", "date", "revenue"]
        ws.append(keys)
        for row in rows:
            ws.append(
                [
                    (
                        "'" + v
                        if isinstance(v, str) and v.startswith(("=", "+", "-", "@"))
                        else v
                    )
                    for v in (row.get(k, "") for k in keys)
                ]
            )
        stream = io.BytesIO()
        book.save(stream)
        stream.seek(0)
        return send_file(
            stream,
            download_name="manifest-laporan.xlsx",
            as_attachment=True,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    @app.get("/api/invoice/<id>.xlsx")
    def invoice_excel(id):
        from openpyxl import Workbook

        _, s = load(g.c)
        permit(g.user, s, "invoice")
        i = item(s["invoices"], id)
        at_branch(g.user, i["origin"])
        require(i["status"] == "issued", "Invoice belum diterbitkan.")
        wb = Workbook()
        ws = wb.active
        ws.append(["Invoice", "Resi", "Kredit"])
        for line in i["lines"]:
            ws.append([i["id"], line["number"], line["value"]])
        stream = io.BytesIO()
        wb.save(stream)
        stream.seek(0)
        return send_file(stream, download_name=id + ".xlsx", as_attachment=True)

    @app.get("/print/<kind>/<id>")
    def print_document(kind, id):
        from .printing import render_document

        _, s = load(g.c)
        return render_document(g.user, s, kind, id)

    @app.get("/")
    def index():
        return send_from_directory(ROOT / "web", "index.html")

    @app.get("/<path:path>")
    def assets(path):
        return send_from_directory(ROOT / "web", path)

    app.connect = connect
    app.dbfile = dbfile
    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=8000)
