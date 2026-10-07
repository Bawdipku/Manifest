"""Build the public Pages demo from the production UI and business rules."""

import json, shutil, zipfile, hashlib, urllib.request, concurrent.futures
from pathlib import Path
import barcode
from importlib.metadata import distribution

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
SITE.mkdir(exist_ok=True)
# site/ contains only generated public demo assets; no server credentials or data.
for name in (
    "app.js",
    "app.css",
    "print.css",
    "favicon.svg",
    "icon-192.png",
    "icon-512.png",
):
    shutil.copyfile(ROOT / "web" / name, SITE / name)
app = (SITE / "app.js").read_text().replace('register("/sw.js")', 'register("./sw.js")')
(SITE / "app.js").write_text(app)
index = (ROOT / "web/index.html").read_text()
for filename in ("manifest.webmanifest", "favicon.svg", "app.css", "app.js"):
    index = index.replace('"/' + filename + '"', '"./' + filename + '"')
index = index.replace(
    "<title>Manifest &amp; SOA</title>", "<title>DEMO · Manifest &amp; SOA</title>"
).replace("<title>Manifest & SOA</title>", "<title>DEMO · Manifest & SOA</title>")
index = index.replace("</head>", '<link rel="stylesheet" href="./demo.css"></head>')
index = index.replace(
    "<body>",
    """<body>
<div class="demo-bar"><div><strong>DEMO · Manifest &amp; SOA</strong><small>Data fiktif · tersimpan di browser ini · akun simulasi · jangan gunakan data asli</small></div><div class="demo-tools"><label>Peran demo<select id="demo-role" class="demo-control" disabled aria-label="Peran demo"></select></label><button id="demo-help" class="demo-control" disabled>Panduan coba</button><button id="demo-reset" class="demo-control" disabled>Reset demo</button></div></div>
<div id="demo-loading" class="demo-loading"><div><span class="mark">M</span><h1>Coba Manifest &amp; SOA</h1><p id="demo-status">Menyiapkan ruang kerja demo…</p><small>Demo berjalan di browser dengan data contoh. Tidak ada akun atau database produksi yang terhubung.</small><p><button id="demo-retry" hidden>Muat ulang</button></p></div></div>
""",
)
index = index.replace(
    '<script src="./app.js"></script>',
    """<script defer src="./vendor/pyodide/pyodide.js"></script><script defer src="./demo.js"></script><script defer src="./app.js"></script>""",
)
index = index.replace(
    "Koneksi terputus. Data tidak dapat disimpan hingga terhubung kembali.",
    "Mode demo lokal. Koneksi diperlukan untuk memuat aplikasi pertama kali.",
)
(SITE / "index.html").write_text(index)
for origin, target in [("adapter.js", "demo.js"), ("demo.css", "demo.css")]:
    shutil.copyfile(ROOT / "demo" / origin, SITE / target)
manifest = json.loads((ROOT / "web/manifest.webmanifest").read_text())
manifest.update(
    name="DEMO · Manifest & SOA", short_name="Manifest Demo", start_url="./", scope="./"
)
for icon in manifest["icons"]:
    icon["src"] = "." + icon["src"]
(SITE / "manifest.webmanifest").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
)
(SITE / "python/backend").mkdir(parents=True, exist_ok=True)
for name in ("__init__.py", "domain.py", "printing.py", "bkc-terms.json"):
    shutil.copyfile(ROOT / "backend" / name, SITE / "python/backend" / name)
shutil.copyfile(ROOT / "demo/runtime.py", SITE / "python/runtime.py")
shutil.copyfile("/usr/share/zoneinfo/Asia/Jakarta", SITE / "python/Jakarta")
package = Path(barcode.__file__).parent
with zipfile.ZipFile(SITE / "python/barcode.zip", "w", zipfile.ZIP_DEFLATED) as bundle:
    for path in package.rglob("*.py"):
        bundle.write(path, "barcode/" + str(path.relative_to(package)))
(SITE / "sw.js").write_text(
    """const CACHE='manifest-prd-demo-v1';const ASSETS=['./','./app.js','./app.css','./demo.js','./demo.css','./manifest.webmanifest','./favicon.svg'];self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(ASSETS)).then(()=>self.skipWaiting())));self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(k=>(k.startsWith('manifest-prd-demo-')||k==='manifest-soa-v1')&&k!==CACHE).map(k=>caches.delete(k)))).then(()=>self.clients.claim())));self.addEventListener('fetch',event=>{const url=new URL(event.request.url);if(event.request.method==='GET'&&url.origin===location.origin)event.respondWith(fetch(event.request).catch(()=>caches.match(event.request)))});\n"""
)
(SITE / "licenses").mkdir(exist_ok=True)
shutil.copyfile(
    ROOT / "demo/PYODIDE-LICENSE.txt", SITE / "licenses/PYODIDE-LICENSE.txt"
)
shutil.copyfile(ROOT / "demo/THIRD_PARTY.md", SITE / "licenses/THIRD_PARTY.md")
barcode_dist = distribution("python-barcode")
for metadata_file in barcode_dist.files:
    if str(metadata_file).endswith("/LICENCE"):
        shutil.copyfile(
            barcode_dist.locate_file(metadata_file),
            SITE / "licenses/PYTHON-BARCODE-LICENSE.txt",
        )
# Remove the old prototype stylesheet after switching to the production UI.
old = SITE / "style.css"
if old.exists():
    old.unlink()
print("Pages demo built from web/ and backend/domain.py.")

# Bundle the pinned browser runtime at build time, so the deployed demo has no CDN dependency.
assets = json.loads((ROOT / "demo/pyodide-assets.json").read_text())
(SITE / "vendor/pyodide").mkdir(parents=True, exist_ok=True)


def fetch_runtime(entry):
    name, expected = entry
    path = SITE / "vendor/pyodide" / name
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
        return
    data = urllib.request.urlopen(
        "https://cdn.jsdelivr.net/pyodide/v0.27.7/full/" + name, timeout=60
    ).read()
    if hashlib.sha256(data).hexdigest() != expected:
        raise RuntimeError("Runtime checksum mismatch: " + name)
    path.write_bytes(data)


with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
    list(pool.map(fetch_runtime, assets.items()))
