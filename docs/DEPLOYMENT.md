# Deploy the full PRD application

The full app runs from `backend/` and `web/`. `site/` is the generated GitHub Pages demo; it runs business rules locally in the browser with fictional records and simulated accounts. It does not run the authenticated PRD backend. The full app uses one same-origin HTTPS server with SQLite storage for records, audit history, accounts, sessions, and protected evidence. No customer data or passwords are included in this repository.

## Server deployment with Docker Compose

Requirements: a Linux server with Docker Compose, a domain pointing at it, ports 80/443 open, and persistent disk. Start with 2 CPU / 2 GB RAM and monitor actual usage. Database writes serialize; validate load for your branch volume before a broad rollout. Keep one application service connected to one local SQLite volume; do not run independent replicas or use a network filesystem for the database.

1. Clone `https://github.com/Bawdipku/Manifest.git` on the server.
2. Copy `.env.example` to `.env` and set `APP_DOMAIN` to your domain.
3. Run `docker compose up -d --build`. Caddy requests and renews HTTPS certificates.
4. Run `docker compose exec -it app python -m backend.admin init-admin --username admin`. Enter a unique password of at least 12 characters at the prompt. There is no default password or public registration.
5. Open `https://YOUR_DOMAIN`, sign in, and create branches, customer/vendor/fleet masters, and staff accounts with their branch scopes.
6. Create a test shipment and perform a receipt/POD/print check before entering real data.

Do not expose the application's internal port 8000 directly. `APP_ORIGIN` and secure cookies are configured by Compose. Keep the database volume and backups private. The repository is public; do not commit `.env`, real shipment exports, evidence, databases, or passwords.

## Local development

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m backend.admin init-admin --username admin
COOKIE_SECURE=false gunicorn --bind 127.0.0.1:8000 'backend.app:create_app()'
```

Open `http://127.0.0.1:8000`. `COOKIE_SECURE=false` is for local HTTP only. Production must use HTTPS and secure cookies. The app shell can be installed as a PWA, but record mutation requires a connection. Records and documents are never cached by the service worker.

## Updates

```sh
git pull --ff-only
docker compose up -d --build
```

The named volume `manifest-data` preserves data across container replacements. **Do not run `docker compose down -v`**, which removes it. Preserve and test a backup before upgrades. The first release creates its schema automatically; future schema changes must include migrations.

## Backup and restore

Use SQLite's online backup API, not a raw copy of a live WAL database:

```sh
docker compose exec app python -m backend.backup /data/backup-2026-10-07.sqlite3
```

The helper refuses to overwrite a backup and runs `PRAGMA integrity_check`. Copy the resulting file to private, encrypted storage outside the server and keep a retention policy. A backup on the same disk alone does not protect against disk loss. Backups contain personal information and session credentials.

Restore while the app is stopped: preserve the failed database for investigation, replace `/data/manifest.sqlite3` with the verified backup, remove stale `manifest.sqlite3-wal` and `manifest.sqlite3-shm` files, ensure ownership is UID 10001, and restart. Clear the `sessions` table in the restored database to revoke old logins. Perform a restore drill on a separate server before field rollout.

## Tests

```sh
pip install pytest==8.4.2
python -m pytest -q
node --check web/app.js
node --check web/sw.js
```

CI runs the same acceptance checks on every push. Physical BKC printing at 100%, barcode scanning, real mobile devices, capacity, and recovery exercises still need validation in the operating environment. Review the supplied BKC terms with the business owner before use.
