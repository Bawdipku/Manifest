# Try the GitHub Pages demo

Open **https://bawdipku.github.io/Manifest/**. No account or password is needed. The first load downloads the browser runtime and may take a few moments. Use a current desktop or mobile browser with JavaScript and local browser storage enabled.

The yellow **DEMO** banner identifies the public demo. Every initial record is fictional. Changes and uploaded sample evidence stay in your browser's IndexedDB, survive a reload, and are not shared with other devices. Do not enter real customer records, actual account passwords, or sensitive evidence. There is no real server authentication here; the role selector is a simulation.

## Suggested walkthrough

1. Start as **Administrator Demo** and open **Panduan coba**.
2. Open **Trip & Manifest**. A draft trip is ready for SOA confirmation and departure; other sample shipments are already in transit or ready for POD.
3. Switch **Peran demo** to **Operasional Hub** and try individual receipt in **Penerimaan Cabang**.
4. Return to Administrator and verify the pending sample report in **Laporan Lapangan**. Switch to Mitra to submit a report for its assigned resi.
5. Try final POD, SOA reconciliation, physical POD returns, invoice payments and reversals, Excel exports, and dynamic five-copy BKC printing.
6. Press **Reset demo** to discard only this browser's demo changes and restore the initial sample records.

The operational rules run from the same Python module as the server application. Browser account selection, local storage, evidence downloads, and audit presentation are demo adapters. Production permissions, shared transactions, and private server storage require the server deployment described in `DEPLOYMENT.md`.

## Build and test

```sh
pip install -r requirements.txt
python scripts/build_demo.py
python -m http.server 8000 --directory site
```

Open `http://localhost:8000`. The build downloads pinned Pyodide 0.27.7 runtime files and verifies their SHA-256 hashes. These assets are served from the same origin as the Pages app; no separate CDN connection is required by visitors. The generated `site/vendor/` directory is intentionally not committed because the Pages workflow recreates it.

Production source under `web/` does not include the demo adapter. The demo has its own clearly named local database and does not connect to production endpoints.
