/* Public demo adapter. Uses the same Python domain functions, entirely in-browser. */
(() => {
  const nativeFetch = window.fetch.bind(window);
  const base = new URL("./", location.href);
  const dbName = "manifest-prd-browser-demo-v1";
  let runtime,
    database,
    persisted = "",
    queue = Promise.resolve();
  const loading = document.querySelector("#demo-loading");
  const status = document.querySelector("#demo-status");
  const roleSelect = document.querySelector("#demo-role");
  const serial = (fn) => {
    const task = queue.then(fn, fn);
    queue = task.catch(() => {});
    return task;
  };
  const dbOpen = () =>
    new Promise((resolve, reject) => {
      const req = indexedDB.open(dbName, 1);
      req.onupgradeneeded = () => req.result.createObjectStore("data");
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  const read = () =>
    new Promise((resolve, reject) => {
      const req = database
        .transaction("data")
        .objectStore("data")
        .get("snapshot");
      req.onsuccess = () => resolve(req.result || "");
      req.onerror = () => reject(req.error);
    });
  const write = (value) =>
    new Promise((resolve, reject) => {
      const tx = database.transaction("data", "readwrite");
      tx.objectStore("data").put(value, "snapshot");
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error);
    });
  const call = (name, ...args) => {
    const fn = runtime.globals.get(name);
    try {
      return fn(...args);
    } finally {
      fn.destroy();
    }
  };
  function chrome(snapshot) {
    const d = JSON.parse(snapshot);
    const selection = d.user_id;
    roleSelect.replaceChildren(
      ...d.accounts
        .filter((a) => a.active)
        .map((a) => {
          const o = document.createElement("option");
          o.value = a.id;
          o.textContent = a.name;
          o.selected = a.id === selection;
          return o;
        }),
    );
  }
  async function persist() {
    const next = call("demo_dump");
    try {
      await write(next);
      persisted = next;
      chrome(next);
    } catch (error) {
      call("demo_restore", persisted);
      throw Error(
        "Penyimpanan browser penuh atau diblokir. Kurangi ukuran bukti atau reset data demo.",
      );
    }
  }
  async function asset(name) {
    const response = await nativeFetch(new URL(name, base));
    if (!response.ok) throw Error("Berkas demo gagal dimuat: " + name);
    return response;
  }
  const ready = (async () => {
    try {
      status.textContent =
        "Menyiapkan demo pertama kali. Unduhan awal dapat memerlukan beberapa saat…";
      database = await dbOpen();
      runtime = await loadPyodide({
        indexURL: new URL("vendor/pyodide/", base).href,
      });
      const files = [
        "backend/__init__.py",
        "backend/domain.py",
        "backend/printing.py",
        "backend/bkc-terms.json",
        "runtime.py",
      ];
      runtime.FS.mkdirTree("/home/pyodide/backend");
      runtime.FS.mkdirTree("/tzdata/Asia");
      const responses = await Promise.all(
        files.map((name) => asset("python/" + name).then((r) => r.text())),
      );
      files.forEach((name, i) =>
        runtime.FS.writeFile("/home/pyodide/" + name, responses[i]),
      );
      const [tz, barcode] = await Promise.all([
        asset("python/Jakarta").then((r) => r.arrayBuffer()),
        asset("python/barcode.zip").then((r) => r.arrayBuffer()),
      ]);
      runtime.FS.writeFile("/tzdata/Asia/Jakarta", new Uint8Array(tz));
      runtime.unpackArchive(barcode, "zip", { extractDir: "/home/pyodide" });
      runtime.runPython(
        "import sys, zoneinfo\nsys.path.insert(0, '/home/pyodide')\nzoneinfo.reset_tzpath(['/tzdata'])\nexec(compile(open('/home/pyodide/runtime.py').read(), '/home/pyodide/runtime.py', 'exec'))",
      );
      persisted = call("demo_restore", await read());
      await write(persisted);
      chrome(persisted);
      loading.hidden = true;
      document
        .querySelectorAll(".demo-control")
        .forEach((e) => (e.disabled = false));
    } catch (error) {
      console.error(error);
      status.textContent =
        "Demo belum dapat dimuat. Periksa koneksi internet dan izinkan penyimpanan browser, lalu muat ulang. " +
        error.message;
      document.querySelector("#demo-retry").hidden = false;
      throw error;
    }
  })();
  // The production app is unchanged. Only this Pages build intercepts its API calls.
  window.fetch = async (input, options = {}) => {
    const url = new URL(
      typeof input === "string" ? input : input.url,
      location.href,
    );
    if (url.origin !== location.origin || !url.pathname.startsWith("/api/"))
      return nativeFetch(input, options);
    await ready;
    return serial(async () => {
      const result = JSON.parse(
        call(
          "demo_request",
          url.pathname + url.search,
          options.method || "GET",
          options.body || "{}",
        ),
      );
      if (result.status < 400 && (options.method || "GET") !== "GET")
        await persist();
      return new Response(JSON.stringify(result.body), {
        status: result.status,
        headers: { "Content-Type": "application/json" },
      });
    });
  };
  roleSelect.addEventListener("change", async () => {
    try {
      await ready;
      await serial(async () => {
        call("demo_switch", roleSelect.value);
        await persist();
      });
      document.querySelector("#dialog").close();
      await window.reload();
    } catch (error) {
      window.notify(error.message);
    }
  });
  document.querySelector("#demo-reset").onclick = async () => {
    if (
      !confirm(
        "Reset semua perubahan demo pada browser ini ke data contoh awal?",
      )
    )
      return;
    try {
      await ready;
      await serial(async () => {
        call("demo_seed");
        await persist();
      });
      location.reload();
    } catch (error) {
      window.notify(error.message);
    }
  };
  document.querySelector("#demo-help").onclick = () =>
    window.openDialog(
      "Cara mencoba demo",
      `<div class="notice">Semua akun adalah simulasi. Data fiktif tersimpan di browser ini dan tidak dibagikan ke perangkat lain. Jangan masukkan data pelanggan, kata sandi, atau bukti transaksi asli.</div><ol class="timeline"><li><strong>Trip & Manifest:</strong> buka trip draft, konfirmasi SOA awal per DEST, lalu catat keberangkatan.</li><li><strong>Penerimaan Cabang:</strong> pilih role Operasional Hub dan terima resi yang tiba. Penerimaan satu resi tidak mengubah seluruh muatan.</li><li><strong>Laporan Lapangan:</strong> kembali ke Administrator, verifikasi laporan contoh. Role Mitra dapat mengirim laporan untuk resi yang ditugaskan.</li><li><strong>POD:</strong> setelah laporan menunggu diverifikasi, catat penerima akhir untuk resi yang siap POD.</li><li><strong>SOA & Rekonsiliasi:</strong> coba selesaikan selisih pada kiriman contoh yang sudah POD.</li><li><strong>Invoice:</strong> lihat invoice contoh, catat pembayaran, atau balikkan pembayaran dengan alasan.</li><li><strong>Pengembalian POD:</strong> buat batch dokumen, lalu konfirmasi penerimaan fisik di cabang asal.</li><li><strong>Penjualan & Resi:</strong> buka Detail untuk melihat riwayat tahap dan mencoba cetak BKC.</li></ol><p>Gunakan <strong>Reset demo</strong> kapan saja untuk memulai ulang.</p>`,
    );
  document.querySelector("#demo-retry").onclick = () => location.reload();
  // Print/export links are also handled locally; no endpoint or upload server exists here.
  document.addEventListener(
    "click",
    async (event) => {
      const a = event.target.closest("a[href]");
      if (!a) return;
      const url = new URL(a.href);
      if (
        url.origin !== location.origin ||
        (!url.pathname.startsWith("/print/") &&
          !url.pathname.startsWith("/api/"))
      )
        return;
      event.preventDefault();
      event.stopPropagation();
      const printing = url.pathname.startsWith("/print/");
      const preview = printing ? window.open("", "_blank") : null;
      try {
        await ready;
        const result = await serial(() =>
          JSON.parse(
            call("demo_request", url.pathname + url.search, "GET", "{}"),
          ),
        );
        if (result.status >= 400) throw Error(result.body.error);
        if (printing) {
          if (!preview) throw Error("Izinkan jendela cetak pada browser.");
          preview.opener = null;
          preview.document.open();
          preview.document.write(
            result.body.html.replace(
              'href="/print.css"',
              'href="' + new URL("print.css", base).href + '"',
            ),
          );
          preview.document.close();
        } else {
          const data = Uint8Array.from(atob(result.body.download), (c) =>
            c.charCodeAt(0),
          );
          const blobURL = URL.createObjectURL(
            new Blob([data], { type: result.body.mime }),
          );
          const download = document.createElement("a");
          download.href = blobURL;
          download.download = result.body.name;
          download.click();
          setTimeout(() => URL.revokeObjectURL(blobURL), 10000);
        }
      } catch (error) {
        preview?.close();
        window.notify(error.message);
      }
    },
    true,
  );
})();
