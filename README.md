# Manifest & SOA PWA

An Indonesian dispatch prototype for creating shipment receipts, assembling trip manifests, and recording departures. The app is in `site/` and deploys to GitHub Pages through `.github/workflows/pages.yml`.

## Run locally

```sh
python -m http.server 8000 --directory site
```

Open `http://localhost:8000`. The app uses fictional demo records. Records added in the app are saved only in that browser's local storage. There are no user accounts, shared server records, branch permissions, POD, SOA reconciliation, invoice processing, or dynamic BKC printing yet. Do not use it for live customer transactions.

The service worker caches the app shell for repeat visits; it does not sync shipment data between devices.
