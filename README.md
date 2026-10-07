# Manifest & SOA

Indonesian cargo operations application based on [PRD 1.6](docs/PRD-1.6.md): sales and barcode BKC, multi-stage manifests, branch receipt, POD, SOA reconciliation, physical document returns, credit invoicing, and reports.

The complete application code is in **`backend/` + `web/`**. It includes authenticated server permissions, persistent SQLite storage, private evidence, audit history, revision checks, and idempotent mutations. A real server is required; GitHub Pages cannot run the backend.

- [Deployment and backup instructions](docs/DEPLOYMENT.md)
- [Implemented scope, tests, and remaining rollout checks](docs/IMPLEMENTATION.md)
- [Acceptance scenarios](tests/test_acceptance.py)

## Run locally

```sh
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python -m backend.admin init-admin --username admin
COOKIE_SECURE=false gunicorn --bind 127.0.0.1:8000 'backend.app:create_app()'
```

Visit `http://127.0.0.1:8000`. Create master branches and users before entering transactions. There is no default administrator password.

## Hosting status

The full app is prepared for server deployment with Docker Compose and HTTPS. Hosting access has not yet been provided.

`site/` remains the earlier [GitHub Pages prototype](https://bawdipku.github.io/Manifest/). Its records are local to each browser. It is not the PRD application's backend and must not be used for real transactions.
