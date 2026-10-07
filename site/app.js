"use strict";
let session = null,
  page = "home",
  query = "",
  reportData = [],
  reportFilters = { view: "sales" },
  pendingRequest = null;
const $ = (s) => document.querySelector(s),
  esc = (v) =>
    String(v ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
const fmt = (v) =>
    new Intl.NumberFormat("id-ID", {
      style: "currency",
      currency: "IDR",
      maximumFractionDigits: 0,
    }).format(v || 0),
  date = (v) =>
    v
      ? new Intl.DateTimeFormat("id-ID", {
          timeZone: "Asia/Jakarta",
          dateStyle: "medium",
          timeStyle: "short",
        }).format(new Date(v))
      : "—";
const localNow = () =>
  new Intl.DateTimeFormat("sv-SE", {
    timeZone: "Asia/Jakarta",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  })
    .format(new Date())
    .replace(" ", "T");
const labels = {
  paid: "Lunas",
  partial: "Sebagian",
  unpaid: "Belum dibayar",
  draft: "Draft",
  registered: "Terdaftar",
  cancelled: "Dibatalkan",
  departed: "Berangkat",
  waiting: "Menunggu berangkat",
  in_transit: "Dalam perjalanan",
  arrived: "Tiba di cabang",
  delivering: "Diantar",
  pod: "POD tercatat",
  waiting_pod: "Menunggu POD",
  waiting_return: "Menunggu kembali",
  returning: "Dalam pengembalian",
  received_origin: "Diterima di asal",
  problem: "Bermasalah",
  received: "Diterima",
  match: "Sesuai",
  difference: "Selisih",
  resolved: "Diselesaikan",
  pending: "Menunggu verifikasi",
  approved: "Disetujui",
  rejected: "Ditolak",
  issued: "Terbit",
  admin: "Administrator",
  counter: "Counter / CS",
  warehouse: "Gudang / Operasional",
  driver: "Kurir / Pengemudi",
  finance: "Finance",
  auditor: "Manajemen / Auditor",
  partner: "Mitra / Agen",
};
const label = (v) => labels[v] || v,
  badge = (v) => `<span class="badge">${esc(label(v))}</span>`,
  button = (title, action, id = "", primary = false) =>
    `<button class="${primary ? "primary" : ""}" data-action="${esc(action)}" data-id="${esc(id)}">${esc(title)}</button>`,
  link = (title, url) =>
    `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(title)}</a>`;
const state = () => session.state,
  can = (op) => session.permissions.includes(op),
  ship = (id) => state().shipments.find((x) => x.id === id),
  trip = (id) => state().trips.find((x) => x.id === id),
  master = (kind, id) => state().masters[kind]?.find((x) => x.id === id),
  branch = (id) => master("branches", id)?.name || id || "—";
const last = (s) => s.legs.at(-1),
  tripLast = (s) => last(s) && trip(last(s).trip_id),
  mine = (b) =>
    session.user.role === "admin" || session.user.branches.includes(b),
  amountTotal = (s) =>
    (s.values?.cash || 0) + (s.values?.credit || 0) + (s.values?.collect || 0);
function notify(message) {
  $("#toast").textContent = message;
  $("#toast").style.display = "block";
  clearTimeout(window.toastTimeout);
  window.toastTimeout = setTimeout(
    () => ($("#toast").style.display = "none"),
    5000,
  );
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": session?.csrf || "",
      ...options.headers,
    },
  });
  let data;
  try {
    data = await response.json();
  } catch {
    throw Error("Server tidak tersedia. Periksa koneksi dan coba kembali.");
  }
  if (!response.ok) {
    if (response.status === 401) {
      session = null;
      $("#app").hidden = true;
      $("#login").hidden = false;
    }
    throw Error(data.error || "Permintaan gagal.");
  }
  return data;
}
async function reload() {
  session = await api("/api/state");
  $("#login").hidden = true;
  $("#app").hidden = false;
  $("#userName").textContent = session.user.name;
  $("#userRole").textContent = label(session.user.role);
  renderNav();
  render();
}
async function mutate(action, payload, key = crypto.randomUUID()) {
  const result = await api("/api/command", {
    method: "POST",
    body: JSON.stringify({
      action,
      payload,
      request_id: key,
      revision: session.revision,
    }),
  });
  await reload();
  return result;
}
function table(headers, rows) {
  return rows.length
    ? `<div class="table"><table><thead><tr>${headers.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>${rows.map((r) => "<tr>" + r.map((c) => "<td>" + c + "</td>").join("") + "</tr>").join("")}</tbody></table></div>`
    : '<div class="empty">Belum ada data yang sesuai.</div>';
}
const fields = {
  text: (name, title, value = "", required = true) => ({
    name,
    title,
    value,
    required,
  }),
  select: (name, title, options, value = "", required = true) => ({
    name,
    title,
    options,
    value,
    required,
    type: "select",
  }),
  number: (name, title, value = 0) => ({
    name,
    title,
    value,
    type: "number",
    min: 0,
    required: true,
  }),
  time: () => ({
    name: "occurred_at",
    title: "Waktu kejadian (WIB)",
    type: "datetime-local",
    value: localNow(),
    required: true,
  }),
  reason: () => ({
    name: "reason",
    title: "Alasan / catatan keputusan",
    type: "textarea",
    required: true,
  }),
  files: () => ({
    name: "files",
    title: "Bukti JPEG / PNG / PDF · maks. 5 × 10 MB",
    type: "file",
    wide: true,
  }),
};
const opts = (rows) => rows.map((r) => [r.id, r.name || r.number || r.id]),
  branchOpts = () => opts(state().masters.branches),
  shipOpts = (rows) =>
    rows.map((s) => [
      s.id,
      `${s.number || "Draft"} · ${s.receiver} · ${s.destination}`,
    ]);
function drawField(f) {
  let input = "";
  const value = f.value ?? "",
    required = f.required ? "required" : "";
  if (f.type === "select")
    input = `<select name="${f.name}" ${required}><option value="">Pilih…</option>${f.options.map(([v, l]) => `<option value="${esc(v)}" ${String(v) === String(value) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>`;
  else if (f.type === "checks")
    input = `<div class="checklist">${f.options.map(([v, l]) => `<label><input type="checkbox" name="${f.name}" value="${esc(v)}" ${(value || []).includes(v) ? "checked" : ""}>${esc(l)}</label>`).join("") || "<small>Tidak ada pilihan tersedia.</small>"}</div>`;
  else if (f.type === "checkbox")
    input = `<input type="checkbox" name="${f.name}" ${value ? "checked" : ""}>`;
  else if (f.type === "textarea")
    input = `<textarea name="${f.name}" ${required}>${esc(value)}</textarea>`;
  else
    input = `<input name="${f.name}" type="${f.type || "text"}" ${f.type === "file" ? 'multiple accept="image/png,image/jpeg,application/pdf"' : `value="${esc(value)}"`} ${f.min !== undefined ? `min="${f.min}"` : ""} ${f.step ? `step="${f.step}"` : ""} ${f.type === "datetime-local" ? 'step="1"' : ""} ${required}>`;
  if (f.type === "select" && ["customer_id", "fleet_id"].includes(f.name))
    input =
      `<input type="search" data-filter-select="${f.name}" aria-label="Cari ${esc(f.title)}" placeholder="Cari ${esc(f.title).toLowerCase()}…">` +
      input;
  return `<label class="${f.wide ? "wide" : ""}">${esc(f.title)}${input}</label>`;
}
function openDialog(title, html) {
  $("#dialogTitle").textContent = title;
  $("#dialogBody").innerHTML = html;
  if (!$("#dialog").open) $("#dialog").showModal();
}
async function fileData(file) {
  if (file.size > 10 * 1024 * 1024)
    throw Error("Setiap berkas maksimal 10 MB.");
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () =>
      resolve({ name: file.name, data: reader.result.split(",")[1] });
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}
function form(title, action, schema, base = {}, transform = (x) => x) {
  const key = crypto.randomUUID();
  openDialog(
    title,
    `<form id="actionForm"><div class="fields">${schema.map(drawField).join("")}</div><p class="form-error" role="alert"></p><div class="form-actions"><button type="button" data-action="close">Batal</button><button class="primary">Simpan</button></div></form>`,
  );
  $("#actionForm").onsubmit = async (ev) => {
    ev.preventDefault();
    const el = ev.currentTarget,
      submit = el.querySelector("button[type=submit],button.primary");
    submit.disabled = true;
    el.querySelector(".form-error").textContent = "";
    try {
      const f = new FormData(el),
        payload = { ...base };
      for (const s of schema) {
        if (s.type === "checks") payload[s.name] = f.getAll(s.name);
        else if (s.type === "checkbox") payload[s.name] = f.has(s.name);
        else if (s.type === "file") {
          const files = el.elements[s.name].files;
          if (files.length > 5) throw Error("Maksimal lima berkas.");
          payload[s.name] = await Promise.all([...files].map(fileData));
        } else if (s.type === "datetime-local")
          payload[s.name] = f.get(s.name) + "+07:00";
        else payload[s.name] = f.get(s.name);
      }
      await mutate(action, transform(payload), key);
      $("#dialog").close();
      notify("Perubahan disimpan.");
    } catch (e) {
      el.querySelector(".form-error").textContent = e.message;
    } finally {
      submit.disabled = false;
    }
  };
}
const navItems = [
  ["home", "Ringkasan", null],
  ["sales", "Penjualan & Resi", "sales"],
  ["trips", "Trip & Manifest", "trip"],
  ["receipts", "Penerimaan Cabang", "receipt"],
  ["pod", "POD", "pod"],
  ["field", "Laporan Lapangan", "report"],
  ["soa", "SOA & Rekonsiliasi", "soa"],
  ["returns", "Pengembalian POD", "receipt"],
  ["invoices", "Invoice", "invoice"],
  ["reports", "Laporan", "reports"],
  ["masters", "Master & Akun", "master"],
];
function renderNav() {
  let nav = navItems.filter(([id, name, p]) => !p || can(p));
  if (session.user.role === "auditor")
    nav.push(["sales", "Riwayat Resi", null]);
  if (!nav.some((x) => x[0] === page)) page = "home";
  $("#nav").innerHTML = nav
    .map(
      ([id, name]) =>
        `<button class="${page === id ? "active" : ""}" data-page="${id}">${name}</button>`,
    )
    .join("");
  $("#title").textContent = nav.find((x) => x[0] === page)?.[1] || "Manifest";
  $("#clock").textContent = date(new Date());
}
function shipmentsTable(rows) {
  return table(
    ["Resi", "Rute", "Penerima", "Status barang", "Dokumen", "Tindakan"],
    rows.map((s) => [
      `<strong>${esc(s.number || "Draft")}</strong><small>${esc(s.ship_date)}</small>`,
      `${esc(branch(s.origin))} → ${esc(s.destination)}`,
      `${esc(s.receiver)}<small>${s.packages} koli · ${s.weight} kg</small>`,
      badge(s.status === "registered" ? s.operational_status : s.status),
      badge(s.document_status),
      button("Detail", "shipment.detail", s.id),
    ]),
  );
}
function render() {
  const s = state();
  renderNav();
  let html = "";
  if (page === "home") {
    const active = s.shipments.filter((x) => x.status === "registered");
    html = `<div class="stats">${[
      ["Resi aktif", active.length],
      [
        "Dalam perjalanan",
        active.filter((x) =>
          ["in_transit", "delivering"].includes(x.operational_status),
        ).length,
      ],
      ["POD tercatat", active.filter((x) => x.pod).length],
      [
        "Menunggu verifikasi",
        s.field_reports.filter((x) => x.status === "pending").length,
      ],
    ]
      .map(
        ([t, n]) => `<article><span>${t}</span><strong>${n}</strong></article>`,
      )
      .join(
        "",
      )}</div><div class="bar"><div><h2>Kiriman terbaru</h2><p>Posisi barang dan pengembalian dokumen dicatat terpisah.</p></div>${can("sales") ? button("+ Buat resi", "shipment.new", "", true) : ""}</div>${shipmentsTable(s.shipments.slice().reverse().slice(0, 8))}<div class="bar"><h2>Tindak lanjut</h2><label>Tanpa pembaruan<select id="followupHours"><option>24</option><option>48</option><option>72</option></select></label></div><div id="followups"></div>`;
  }
  if (page === "sales")
    html = `<div class="bar"><p>Snapshot pengirim disimpan saat pencatatan transaksi.</p>${can("sales") ? button("+ Buat resi", "shipment.new", "", true) : ""}</div><input class="search" id="search" placeholder="Cari atau scan nomor resi, lalu Enter" value="${esc(query)}" aria-label="Cari resi"><div id="salesRows">${shipmentsTable(s.shipments.filter((x) => JSON.stringify([x.number, x.receiver, x.sender.name]).toLowerCase().includes(query.toLowerCase())))}</div>`;
  if (page === "trips")
    html =
      `<div class="bar"><p>Manifest lama tetap tersedia pada riwayat perjalanan.</p>${button("+ Buat trip", "trip.new", "", true)}</div>` +
      s.trips
        .slice()
        .reverse()
        .map(
          (t) =>
            `<article class="card"><div class="bar"><div><h3>${esc(t.id)} ${badge(t.status)}</h3><span class="meta">${esc(branch(t.origin))} → ${esc(branch(t.destination))} · ${t.type} · ${t.mode === "transit" ? "Transit / hub" : "Tujuan akhir"} · ${esc(t.driver)} · ${esc(t.vehicle)}</span></div>${link("Cetak surat jalan", "/print/trip/" + t.id)}</div><p>${t.shipment_ids.map((id) => button(ship(id)?.number || id, "shipment.detail", id)).join(" ") || "Belum ada muatan."}</p><div class="actions">${mine(t.origin) && t.status === "draft" ? button("Tambah muatan", "trip.add", t.id) + button("Lepas muatan", "trip.remove", t.id) + button("Berangkatkan", "trip.depart", t.id, true) : ""}${can("soa") && mine(t.origin) && t.status === "draft" ? button("Konfirmasi SOA awal", "soa.confirm", t.id) : ""}${mine(t.origin) && t.executor === "vendor" && t.status === "departed" && !t.handover_at ? button("Serah terima vendor", "trip.handover", t.id) : ""}</div></article>`,
        )
        .join("");
  if (page === "receipts") {
    const rows = s.shipments.filter(
      (x) =>
        x.status === "registered" &&
        !x.pod &&
        tripLast(x)?.type === "P2P" &&
        tripLast(x)?.status === "departed" &&
        !last(x)?.received_at &&
        mine(last(x).destination),
    );
    html =
      '<div class="bar"><p>Catat hanya resi yang benar-benar tiba. Resi lain tetap dalam perjalanan.</p></div>' +
      table(
        ["Resi", "Asal tahap", "Tujuan tahap", "Penerima", "Tindakan"],
        rows.map((x) => [
          esc(x.number),
          esc(branch(last(x).origin)),
          esc(branch(last(x).destination)),
          esc(x.receiver),
          button("Terima resi", "receipt.record", x.id, true),
        ]),
      );
  }
  if (page === "pod") {
    const rows = s.shipments.filter(
      (x) =>
        x.status === "registered" &&
        tripLast(x)?.type === "P2D" &&
        tripLast(x)?.status === "departed" &&
        mine(last(x).origin),
    );
    html =
      '<div class="bar"><p>POD mencatat penerima akhir. Gunakan pengembalian POD untuk dokumen fisik.</p></div>' +
      table(
        ["Resi", "Penerima", "Status", "Tindakan"],
        rows.map((x) => [
          esc(x.number),
          esc(x.receiver),
          badge(x.operational_status),
          x.pod
            ? button("Lihat POD", "shipment.detail", x.id)
            : button("Catat POD", "pod.record", x.id, true),
        ]),
      );
  }
  if (page === "field")
    html =
      `<div class="bar"><p>Laporan lapangan menunggu persetujuan administrator.</p>${button("+ Kirim laporan", "field.submit", "", true)}</div>` +
      table(
        ["Resi / sumber", "Jenis", "Waktu kejadian", "Status", "Tindakan"],
        s.field_reports
          .slice()
          .reverse()
          .map((r) => [
            `${esc(ship(r.shipment_id)?.number)}<small>${esc(r.reporter)} · ${esc(r.source)}</small>`,
            esc(r.kind),
            esc(date(r.occurred_at)),
            badge(r.status),
            button("Lihat", "field.detail", r.id) +
              (can("review") && r.status === "pending"
                ? button("Verifikasi", "field.review", r.id)
                : "") +
              (r.issue_open && can("review")
                ? button("Selesaikan kendala", "field.resolve", r.id)
                : ""),
          ]),
      );
  if (page === "soa")
    html =
      `<div class="notice">SOA sementara adalah snapshot. SOA asli dicatat setelah POD dan tidak menimpa snapshot.</div><div class="bar">${can("soa") ? button("Konfirmasi kelompok awal", "soa.pick") : ""}</div>` +
      table(
        ["Resi", "Sementara", "Kebijakan", "Asli / hasil", "Tindakan"],
        s.shipments
          .filter((x) => x.soa)
          .map((x) => [
            esc(x.number),
            fmt(x.soa.value) + `<small>Versi ${x.soa.version}</small>`,
            `${esc(x.soa.policy)} ${x.soa.provisional ? badge("Provisional") : ""}`,
            x.actual_soa
              ? fmt(x.actual_soa.value) + " " + badge(x.actual_soa.status)
              : "—",
            button("Riwayat", "shipment.detail", x.id) +
              (x.pod ? button("Catat / revisi asli", "soa.actual", x.id) : "") +
              (x.actual_soa ? button("Selesaikan", "soa.resolve", x.id) : "") +
              (x.soa.provisional && session.user.role === "admin"
                ? button("Setujui kebijakan", "soa.approve_policy", x.id)
                : ""),
          ]),
      );
  if (page === "returns")
    html =
      `<div class="bar"><p>Konfirmasi fisik hanya oleh cabang asal.</p>${button("+ Batch pengembalian", "return.create", "", true)}</div>` +
      table(
        ["Referensi", "Resi", "Cabang asal", "Status", "Tindakan"],
        s.returns.map((r) => [
          esc(r.reference),
          r.shipment_ids.map((id) => esc(ship(id)?.number)).join("<br>"),
          esc(branch(r.destination)),
          badge(r.status),
          r.status === "returning" && mine(r.destination)
            ? button("Terima fisik", "return.receive", r.id) +
              button("Masalah dokumen", "return.problem", r.id)
            : esc(r.note || ""),
        ]),
      );
  if (page === "invoices")
    html =
      `<div class="bar"><p>Tagihan berasal dari nilai kredit. Invoice tidak menambah omzet.</p>${button("+ Buat invoice", "invoice.create", "", true)}</div>` +
      table(
        ["Invoice", "Pelanggan", "Nilai / saldo", "Status", "Tindakan"],
        s.invoices.map((i) => {
          const paid = i.payments
            .filter((p) => !p.reversed)
            .reduce((n, p) => n + p.value, 0);
          return [
            esc(i.id),
            esc(
              i.customer_snapshot?.name ||
                master("customers", i.customer_id)?.name,
            ),
            i.total !== undefined
              ? fmt(i.total) + `<small>Saldo ${fmt(i.total - paid)}</small>`
              : "Belum terbit",
            badge(i.status),
            button("Rincian", "invoice.detail", i.id) +
              (i.status === "draft"
                ? button("Terbitkan", "invoice.issue", i.id)
                : "") +
              (i.status === "issued"
                ? button("Pembayaran", "payment.record", i.id)
                : ""),
          ];
        }),
      );
  if (page === "reports")
    html = `<form id="reportFilters" class="filters"><label>Jenis<select name="view">${[
      ["sales", "Penjualan tercatat"],
      ["departed", "Kiriman diberangkatkan"],
      ["reconciliation", "Rekonsiliasi"],
      ["cancelled", "Pembatalan"],
      ["finance", "Penyelesaian keuangan"],
      ["documents", "Dokumen POD"],
    ]
      .map(
        ([v, l]) =>
          `<option value="${v}" ${reportFilters.view === v ? "selected" : ""}>${l}</option>`,
      )
      .join(
        "",
      )}</select></label><label>Dari (WIB)<input type="date" name="from" value="${esc(reportFilters.from || "")}"></label><label>Sampai (WIB)<input type="date" name="to" value="${esc(reportFilters.to || "")}"></label><label>Cabang<select name="branch"><option value="">Semua cakupan</option>${branchOpts()
      .map(
        ([v, l]) =>
          `<option value="${v}" ${reportFilters.branch === v ? "selected" : ""}>${esc(l)}</option>`,
      )
      .join(
        "",
      )}</select></label><label>Status<input name="status" value="${esc(reportFilters.status || "")}" placeholder="Contoh: pod"></label><label>Resi<input name="q" value="${esc(reportFilters.q || "")}"></label><button class="primary">Tampilkan</button></form><div class="bar"><p>Setiap penjualan dihitung satu kali.</p><div class="actions">${link("Ekspor Excel", "/api/reports.xlsx?" + new URLSearchParams(reportFilters))}${button("Cetak", "report.print")}${["admin", "finance"].includes(session.user.role) ? button("Arsipkan snapshot", "report.archive") : ""}</div></div><div id="reportRows">${renderReports()}</div><h3>Arsip tersimpan</h3>${table(
      ["Arsip", "Tanggal", "Tindakan"],
      s.archives.map((a) => [
        esc(a.id),
        esc(date(a.created_at)),
        button("Lihat snapshot", "archive.detail", a.id),
      ]),
    )}`;
  if (page === "masters") html = renderMasters();
  $("#content").innerHTML = html;
  if (page === "home") renderFollowups();
}
function renderFollowups() {
  const hours = Number($("#followupHours")?.value || 24);
  const rows = state()
    .shipments.filter((s) => s.status === "registered" && !s.pod)
    .filter((s) => {
      const updates = state()
        .field_reports.filter((r) => r.shipment_id === s.id)
        .map((r) => r.recorded_at);
      const lastTime = [
        s.created_at,
        ...s.legs.flatMap((l) =>
          [l.departed_at, l.received_at].filter(Boolean),
        ),
        ...updates,
      ]
        .sort()
        .at(-1);
      return (
        state().field_reports.some(
          (r) => r.shipment_id === s.id && r.issue_open,
        ) || Date.now() - new Date(lastTime) > hours * 3600000
      );
    });
  $("#followups").innerHTML = shipmentsTable(rows);
}
function renderReports() {
  if (reportFilters.view === "finance")
    return table(
      [
        "Invoice",
        "Tanggal WIB",
        "Cabang",
        "Pelanggan",
        "Status",
        "Tagihan",
        "Dibayar",
        "Saldo",
      ],
      reportData.map((r) => [
        esc(r.number),
        esc(r.date),
        esc(branch(r.origin)),
        esc(r.destination),
        badge(r.status),
        fmt(r.invoice_total),
        fmt(r.paid),
        fmt(r.balance),
      ]),
    );
  return table(
    [
      "Resi",
      "Tanggal WIB",
      "Asal",
      "Tujuan",
      "Status",
      "Penjualan",
      "SOA asli",
      "Dokumen",
    ],
    reportData.map((r) => [
      esc(r.number),
      esc(r.date),
      esc(branch(r.origin)),
      esc(r.destination),
      badge(r.sales_status === "cancelled" ? "cancelled" : r.status),
      r.revenue !== undefined ? fmt(r.revenue) : "—",
      r.soa_actual !== undefined ? fmt(r.soa_actual) : "—",
      badge(r.document_status),
    ]),
  );
}
const masterLabels = {
  branches: "Cabang",
  cities: "Kota",
  employees: "Pegawai",
  customers: "Pelanggan",
  fleet: "Armada",
  rates: "Tarif referensi",
  products: "Produk",
  units: "Satuan",
  vendors: "Vendor",
};
function renderMasters() {
  return (
    `<div class="notice">Mulai dengan cabang, pelanggan, dan armada. Perubahan master tidak mengganti snapshot transaksi lama.</div>` +
    Object.entries(masterLabels)
      .map(
        ([kind, title]) =>
          `<article class="card"><div class="bar"><h2>${title}</h2>${button("+ Tambah", "master.new", kind)}</div>${table(
            ["Nama", "Keterangan", "Status", ""],
            (state().masters[kind] || []).map((x) => [
              esc(x.name),
              esc(
                x.prefix || x.plate || x.contact || x.address || x.note || "",
              ),
              badge(x.active === false ? "Nonaktif" : "Aktif"),
              button("Ubah", "master.edit", kind + "|" + x.id),
            ]),
          )}</article>`,
      )
      .join("") +
    `<article class="card"><div class="bar"><h2>Akun & cakupan cabang</h2>${button("+ Buat akun", "account.new")}</div>${table(
      ["Nama", "Peran", "Cabang", "Status", ""],
      session.accounts.map((a) => [
        esc(a.name) + "<small>" + esc(a.username) + "</small>",
        esc(label(a.role)),
        a.branches.map(branch).map(esc).join(", ") || "Semua",
        badge(a.active ? "Aktif" : "Nonaktif"),
        button("Ubah", "account.edit", a.id),
      ]),
    )}</article><article class="card"><h2>Riwayat audit</h2>${button("Lihat 200 perubahan terakhir", "audit.view")}</article><article class="card"><h2>Template izin peran</h2>${button("Atur template", "permissions.edit")}<p class="muted">Perubahan izin berlaku pada server untuk semua akun dalam peran tersebut.</p></article>`
  );
}
function shipmentForm(s = null) {
  let schema = [
    fields.select(
      "origin",
      "Cabang asal",
      branchOpts(),
      s?.origin || session.user.branches[0],
    ),
    fields.select(
      "final_branch",
      "Cabang penerima akhir",
      branchOpts(),
      s?.final_branch,
    ),
    fields.text(
      "destination",
      "Kota tujuan akhir (DEST)",
      s?.destination || "",
    ),
    fields.select(
      "customer_id",
      "Pelanggan terdaftar",
      opts(state().masters.customers || []),
      s?.customer_id,
      false,
    ),
    fields.text("sender", "Nama pengirim", s?.sender.name || "", false),
    fields.text(
      "sender_address",
      "Alamat pengirim",
      s?.sender.address || "",
      false,
    ),
    fields.text(
      "sender_contact",
      "Kontak pengirim",
      s?.sender.contact || "",
      false,
    ),
    fields.text("receiver", "Nama penerima", s?.receiver || ""),
    fields.text("address", "Alamat penerima", s?.address || ""),
    fields.text("contact", "Kontak penerima", s?.contact || "", false),
    fields.text(
      "description",
      "Isi / keterangan muatan",
      s?.description || "",
      false,
    ),
    fields.text("reference", "Referensi", s?.reference || "", false),
    { ...fields.number("packages", "Koli", s?.packages || 1), min: 1 },
    {
      ...fields.number("weight", "Berat (kg)", s?.weight || 1),
      min: 0.01,
      step: 0.01,
    },
    {
      name: "ship_date",
      title: "Tanggal kirim (WIB)",
      type: "date",
      value: s?.ship_date || localNow().slice(0, 10),
      required: true,
    },
    ...Object.entries({
      cash: "Tunai",
      credit: "Kredit",
      collect: "Tagih tujuan",
      forwarding: "Biaya penerus",
    }).map(([k, l]) => fields.number(k, l + " (Rp)", s?.values[k] || 0)),
    {
      name: "register",
      title: "Daftarkan dan terbitkan nomor resi",
      type: "checkbox",
      value: false,
    },
  ];
  form(
    s ? "Ubah draft resi" : "Buat penjualan & resi",
    "shipment.save",
    schema,
    s ? { id: s.id } : {},
  );
  const customer = $("#actionForm [name=customer_id]");
  customer.onchange = () => {
    const c = master("customers", customer.value);
    if (c) {
      for (const [key, val] of Object.entries({
        sender: c.name,
        sender_address: c.address,
        sender_contact: c.contact,
      }))
        $("#actionForm").elements[key].value = val || "";
    }
  };
}
async function details(id) {
  const s = ship(id);
  openDialog(
    s.number || "Draft resi",
    `<div class="details">${[
      ["Pengirim", s.sender.name],
      ["Penerima", s.receiver],
      ["Alamat", s.address],
      ["Asal / tujuan", branch(s.origin) + " → " + s.destination],
      ["Muatan", s.packages + " koli · " + s.weight + " kg"],
      ["Dokumen", label(s.document_status)],
    ]
      .map(([k, v]) => `<div><small>${esc(k)}</small><p>${esc(v)}</p></div>`)
      .join(
        "",
      )}</div>${s.values ? `<p>Tunai ${fmt(s.values.cash)} · Kredit ${fmt(s.values.credit)} · Tagih tujuan ${fmt(s.values.collect)} · Biaya penerus ${fmt(s.values.forwarding)}</p>` : ""}<div class="actions">${s.number && s.values ? link("Cetak 5 lembar BKC", "/print/shipment/" + s.id) : ""}${can("sales") && s.status === "draft" ? button("Ubah / daftarkan", "shipment.edit", s.id) : ""}${(can("sales") || can("cancel")) && s.status !== "cancelled" ? button("Batalkan resi", "shipment.cancel", s.id) : ""}${can("assign") ? button("Tugaskan kurir / mitra", "assignment.save", s.id) : ""}</div><h3>Riwayat tahap</h3><ol class="timeline">${s.legs.map((l) => `<li><strong>${esc(l.trip_id)}</strong> · ${esc(branch(l.origin))} → ${esc(branch(l.destination))}<br><small>Berangkat: ${esc(date(l.departed_at))} · Diterima: ${esc(date(l.received_at))}</small></li>`).join("") || "<li>Belum dimanifestkan.</li>"}</ol>${s.pod ? `<h3>POD penerima akhir</h3><p>${esc(s.pod.receiver)} · ${esc(date(s.pod.occurred_at))}</p><p>${esc(s.pod.exception_reason || "")}</p>${s.pod.evidence_ids.map((id) => link("Unduh bukti", "/api/evidence/" + id)).join(" · ")}` : ""}${s.soa ? `<h3>SOA sementara · versi ${s.soa.version}</h3><p>${fmt(s.soa.value)} · ${esc(s.soa.policy)} ${s.soa.provisional ? "(provisional)" : ""}</p><details><summary>Snapshot sebelumnya</summary><pre>${esc(JSON.stringify(s.soa_history, null, 2))}</pre></details>` : ""}${s.actual_soa ? `<h3>SOA asli</h3><p>${fmt(s.actual_soa.value)} · ${badge(s.actual_soa.status)}</p><p>${esc(s.actual_soa.resolution || s.actual_soa.reason || "")}</p><details><summary>Riwayat revisi SOA asli</summary><pre>${esc(JSON.stringify(s.actual_history || [], null, 2))}</pre></details>` : ""}<h3>Riwayat transaksi</h3><div id="history">Memuat…</div>`,
  );
  try {
    const d = await api("/api/history/" + id);
    if ($("#history"))
      $("#history").innerHTML = table(
        ["Waktu", "Tindakan", "Pelaku", "Alasan"],
        d.events.map((x) => [
          esc(date(x.at)),
          esc(x.action),
          esc(x.actor),
          esc(x.reason),
        ]),
      );
  } catch (e) {
    if ($("#history")) $("#history").textContent = e.message;
  }
}
function masterForm(kind, id) {
  const old = (state().masters[kind] || []).find((x) => x.id === id);
  let schema = [fields.text("name", "Nama", old?.name || "")];
  const extra = {
    branches: [
      ["office_code", "Kode kantor"],
      ["city_code", "Kode kota"],
      ["prefix", "Prefix barcode"],
      ["controller", "Cabang pengendali"],
    ],
    cities: [["code", "Kode kota"]],
    employees: [
      ["contact", "Kontak"],
      ["position", "Jabatan"],
    ],
    customers: [
      ["address", "Alamat"],
      ["contact", "Kontak"],
    ],
    fleet: [
      ["plate", "Nomor polisi"],
      ["capacity", "Kapasitas"],
    ],
    rates: [
      ["origin", "Asal"],
      ["destination", "Tujuan"],
      ["value", "Tarif referensi"],
    ],
    products: [["note", "Keterangan"]],
    units: [["symbol", "Singkatan"]],
    vendors: [
      ["address", "Alamat"],
      ["contact", "Kontak"],
    ],
  };
  schema.push(
    ...extra[kind].map(([k, l]) =>
      fields.text(
        k,
        l,
        old?.[k] || "",
        (kind === "branches" && k !== "controller") || k === "plate",
      ),
    ),
    {
      name: "active",
      title: "Aktif",
      type: "checkbox",
      value: old?.active !== false,
    },
  );
  form("Master " + masterLabels[kind], "master.save", schema, {
    kind,
    ...(old ? { id: old.id } : {}),
  });
}
function accountForm(id) {
  const old = session.accounts.find((x) => x.id === id);
  form(
    old ? "Ubah akun" : "Buat akun",
    "account.save",
    [
      fields.text("username", "Nama pengguna", old?.username || ""),
      fields.text("name", "Nama lengkap", old?.name || ""),
      {
        name: "password",
        title: old
          ? "Kata sandi baru (kosong = tetap)"
          : "Kata sandi (minimal 12 karakter)",
        type: "password",
        required: !old,
      },
      fields.select(
        "role",
        "Peran",
        Object.keys(labels)
          .filter((x) =>
            [
              "admin",
              "counter",
              "warehouse",
              "driver",
              "finance",
              "auditor",
              "partner",
            ].includes(x),
          )
          .map((x) => [x, label(x)]),
        old?.role || "counter",
      ),
      {
        name: "branches",
        title: "Cakupan cabang",
        type: "checks",
        options: branchOpts(),
        value: old?.branches || [],
        wide: true,
      },
      fields.select(
        "vendor_id",
        "Vendor untuk mitra",
        opts(state().masters.vendors || []),
        old?.vendor_id || "",
        false,
      ),
      {
        name: "active",
        title: "Akun aktif",
        type: "checkbox",
        value: old?.active !== 0,
      },
    ],
    old ? { id: old.id } : {},
  );
}
async function action(name, id) {
  const s = state();
  if (name === "close") return $("#dialog").close();
  if (name === "shipment.new") return shipmentForm();
  if (name === "shipment.edit") return shipmentForm(ship(id));
  if (name === "shipment.detail") return details(id);
  if (name === "shipment.cancel")
    return form("Batalkan resi", name, [fields.reason()], { id });
  if (name === "assignment.save")
    return form(
      "Penugasan kurir / mitra",
      name,
      [
        fields.select(
          "user_id",
          "Akun yang ditugaskan",
          session.accounts
            .filter((x) => ["partner", "driver"].includes(x.role) && x.active)
            .map((x) => [x.id, x.name]),
          ship(id).assigned_to,
          false,
        ),
      ],
      { id },
    );
  if (name === "trip.new")
    return form("Buat trip", "trip.create", [
      fields.select(
        "origin",
        "Cabang asal tahap",
        branchOpts(),
        session.user.branches[0],
      ),
      fields.select("destination", "Cabang tujuan tahap", branchOpts()),
      fields.select(
        "type",
        "Jenis tahap",
        [
          ["P2P", "P2P · Antarcabang"],
          ["P2D", "P2D · Ke penerima"],
        ],
        "P2P",
      ),
      fields.select(
        "mode",
        "Tujuan P2P",
        [
          ["transit", "Transit / hub"],
          ["final", "Cabang tujuan akhir"],
        ],
        "final",
      ),
      fields.select(
        "executor",
        "Pelaksana",
        [
          ["internal", "Internal"],
          ["vendor", "Vendor"],
        ],
        "internal",
      ),
      fields.select(
        "vendor_id",
        "Vendor",
        opts(s.masters.vendors || []),
        "",
        false,
      ),
      fields.text(
        "vendor_reference",
        "Referensi surat jalan vendor",
        "",
        false,
      ),
      fields.text("driver", "Pengemudi / pelaksana"),
      fields.select(
        "fleet_id",
        "Armada",
        opts(s.masters.fleet || []),
        "",
        false,
      ),
      fields.text(
        "vehicle",
        "Nomor polisi (jika tidak memilih armada)",
        "",
        false,
      ),
      {
        name: "planned_date",
        title: "Tanggal rencana",
        type: "date",
        value: localNow().slice(0, 10),
        required: true,
      },
    ]);
  if (name === "trip.add") {
    const t = trip(id),
      rows = s.shipments.filter(
        (x) =>
          x.status === "registered" &&
          !x.pod &&
          (!last(x) || last(x).received_at) &&
          (last(x)?.destination || x.origin) === t.origin &&
          (t.type === "P2P"
            ? t.mode === "transit" || x.final_branch === t.destination
            : x.final_branch === t.origin),
      );
    form(
      "Tambah muatan (maks. 200 resi)",
      name,
      [
        fields.text("scan", "Scan nomor resi lalu Enter", "", false),
        {
          name: "shipment_ids",
          title: "Resi tersedia",
          type: "checks",
          options: shipOpts(rows),
          wide: true,
        },
      ],
      { id },
      (p) => {
        delete p.scan;
        return p;
      },
    );
    $("#actionForm [name=scan]").onkeydown = (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        const target = rows.find((x) => x.number === e.target.value.trim());
        if (target) {
          const checkbox = [
            ...$("#actionForm").querySelectorAll("[name=shipment_ids]"),
          ].find((x) => x.value === target.id);
          checkbox.checked = true;
          e.target.value = "";
          notify("Resi dipilih.");
        } else notify("Resi tidak tersedia untuk trip ini.");
      }
    };
    return;
  }
  if (name === "trip.remove")
    return form(
      "Lepas dari draft manifest",
      name,
      [
        fields.select(
          "shipment_id",
          "Resi",
          shipOpts(trip(id).shipment_ids.map(ship)),
        ),
        fields.reason(),
      ],
      { id },
    );
  if (name === "trip.depart")
    return form("Catat keberangkatan", name, [fields.time()], { id });
  if (name === "trip.handover")
    return form(
      "Serah terima vendor",
      name,
      [fields.time(), fields.text("reference", "Referensi serah terima")],
      { id },
    );
  if (name === "receipt.record")
    return form(
      "Penerimaan individual di cabang",
      name,
      [
        fields.time(),
        fields.text("condition", "Kondisi barang", "Baik"),
        fields.text("note", "Catatan", "", false),
      ],
      { id },
    );
  if (name === "pod.record")
    return form(
      "POD penerima akhir",
      name,
      [
        fields.text("receiver", "Nama penerima"),
        fields.time(),
        fields.files(),
        fields.text(
          "exception_reason",
          "Alasan jika bukti tidak tersedia",
          "",
          false,
        ),
      ],
      { id },
    );
  if (name === "field.submit")
    return form("Kirim laporan lapangan", name, [
      fields.select(
        "shipment_id",
        "Resi",
        shipOpts(
          s.shipments.filter((x) => x.status === "registered" && !x.pod),
        ),
      ),
      fields.select(
        "kind",
        "Jenis laporan",
        [
          ["arrival", "Tiba di tujuan tahap"],
          ["pod", "Diterima penerima akhir"],
          ["issue", "Kendala pengiriman"],
        ],
        "arrival",
      ),
      fields.text("reporter", "Nama pelapor", session.user.name),
      fields.text("contact", "Kontak pelapor"),
      fields.select(
        "source",
        "Sumber",
        [
          ["portal", "Portal langsung"],
          ["whatsapp", "WhatsApp"],
          ["phone", "Telepon"],
          ["email", "Email"],
          ["in_person", "Tatap muka"],
        ],
        "portal",
      ),
      fields.time(),
      fields.text("receiver", "Nama penerima (untuk POD)", "", false),
      fields.text(
        "condition",
        "Kondisi (untuk penerimaan cabang)",
        "Baik",
        false,
      ),
      { name: "note", title: "Catatan / kendala", type: "textarea" },
      fields.files(),
    ]);
  if (name === "field.detail") {
    const r = s.field_reports.find((x) => x.id === id);
    return openDialog(
      "Laporan " + id,
      `<p>${esc(ship(r.shipment_id)?.number)} · ${badge(r.status)}</p><p>${esc(r.reporter)} · ${esc(r.contact)} · ${esc(r.source)}</p><p>Kejadian ${esc(date(r.occurred_at))}<br>Dicatat ${esc(date(r.recorded_at))}</p><p>${esc(r.note)}</p><p>${esc(r.receiver)} · ${esc(r.condition)}</p><p>${r.evidence_ids.map((id, i) => link("Bukti " + (i + 1), "/api/evidence/" + id)).join(" · ") || "Tanpa bukti."}</p><p>${esc(r.review_reason || "")}</p>`,
    );
  }
  if (name === "field.review")
    return form(
      "Verifikasi laporan mitra",
      name,
      [
        fields.select("decision", "Keputusan", [
          ["approved", "Setujui"],
          ["rejected", "Tolak"],
        ]),
        fields.reason(),
      ],
      { id },
    );
  if (name === "field.resolve")
    return form("Selesaikan kendala", name, [fields.reason()], { id });
  if (name === "soa.pick") {
    openDialog(
      "Pilih trip awal",
      s.trips
        .filter((t) => t.status === "draft" && mine(t.origin))
        .map(
          (t) =>
            `<p>${button(t.id + " · " + branch(t.origin) + " → " + branch(t.destination), "soa.confirm", t.id)}</p>`,
        )
        .join("") || "<p>Tidak ada draft trip.</p>",
    );
    return;
  }
  if (name === "soa.confirm") {
    const t = trip(id),
      rows = t.shipment_ids.map(ship).filter((s) => s.legs.length === 1),
      destinations = [...new Set(rows.map((s) => s.destination))];
    if (!destinations.length) return notify("Tidak ada muatan tahap pertama.");
    openDialog(
      "Pilih kelompok DEST",
      destinations
        .map(
          (d) =>
            `<p><button data-action="soa.group" data-id="${esc(id + "|" + d)}">${esc(d)}</button></p>`,
        )
        .join(""),
    );
    return;
  }
  if (name === "soa.group") {
    const split = id.indexOf("|"),
      tid = id.slice(0, split),
      dest = id.slice(split + 1),
      rows = trip(tid)
        .shipment_ids.map(ship)
        .filter((s) => s.legs.length === 1 && s.destination === dest);
    return form(
      "Konfirmasi SOA · " + dest,
      "soa.confirm",
      [
        fields.text("policy", "Kebijakan SOA"),
        {
          name: "provisional",
          title: "Kebijakan masih provisional",
          type: "checkbox",
        },
        fields.reason(),
        ...rows.map((s) =>
          fields.number("value_" + s.id, s.number + " (Rp)", s.soa?.value || 0),
        ),
      ],
      { trip_id: tid, destination: dest },
      (p) => {
        p.amounts = {};
        for (const s of rows) {
          p.amounts[s.id] = p["value_" + s.id];
          delete p["value_" + s.id];
        }
        return p;
      },
    );
  }
  if (name === "soa.actual")
    return form(
      "Catat / revisi SOA asli",
      name,
      [
        fields.number(
          "value",
          "SOA asli (Rp)",
          ship(id).actual_soa?.value || 0,
        ),
        fields.reason(),
      ],
      { id },
    );
  if (name === "soa.resolve" || name === "soa.approve_policy")
    return form(
      name === "soa.resolve"
        ? "Selesaikan selisih"
        : "Setujui kebijakan provisional",
      name,
      [fields.reason()],
      { id },
    );
  if (name === "return.create")
    return form("Buat batch pengembalian POD", name, [
      fields.text("reference", "Referensi batch"),
      {
        name: "shipment_ids",
        title: "Dokumen ke satu cabang asal",
        type: "checks",
        options: shipOpts(
          s.shipments.filter(
            (x) =>
              x.pod &&
              ["waiting_return", "problem"].includes(x.document_status) &&
              mine(x.final_branch),
          ),
        ),
        wide: true,
      },
    ]);
  if (name === "return.receive" || name === "return.problem")
    return form(
      name === "return.receive"
        ? "Konfirmasi penerimaan fisik"
        : "Catat masalah dokumen",
      name,
      [fields.text("note", "Catatan")],
      { id },
    );
  if (name === "invoice.create")
    return form("Buat draft invoice", name, [
      {
        name: "shipment_ids",
        title: "Resi kredit · satu pelanggan dan cabang",
        type: "checks",
        wide: true,
        options: shipOpts(
          s.shipments.filter(
            (x) =>
              x.status === "registered" &&
              x.customer_id &&
              x.values?.credit > 0 &&
              !s.invoices.some(
                (i) =>
                  i.status !== "cancelled" && i.shipment_ids.includes(x.id),
              ),
          ),
        ),
      },
    ]);
  if (name === "invoice.issue")
    return form("Terbitkan invoice", name, [], { id });
  if (name === "invoice.cancel")
    return form("Batalkan invoice", name, [fields.reason()], { id });
  if (name === "payment.record")
    return form(
      "Catat pembayaran",
      name,
      [
        fields.number("value", "Nilai pembayaran (Rp)"),
        fields.text("reference", "Referensi pembayaran unik"),
        fields.time(),
      ],
      { id },
    );
  if (name === "payment.reverse") {
    const [invoice, payment] = id.split("|");
    return form("Balikkan pembayaran", name, [fields.reason()], {
      id: invoice,
      payment_id: payment,
    });
  }
  if (name === "invoice.detail") {
    const i = s.invoices.find((x) => x.id === id);
    return openDialog(
      "Invoice " + id,
      `<p>${badge(i.status)} · ${esc(i.customer_snapshot?.name || master("customers", i.customer_id)?.name)}</p>${table(
        ["Resi", "Kredit"],
        (
          i.lines ||
          i.shipment_ids.map((id) => ({
            number: ship(id)?.number,
            value: ship(id)?.values?.credit,
          }))
        ).map((x) => [esc(x.number), fmt(x.value)]),
      )}<h3>Riwayat pembayaran</h3>${table(
        ["Referensi", "Nilai", "Waktu", "Status", ""],
        i.payments.map((p) => [
          esc(p.reference),
          fmt(p.value),
          esc(date(p.occurred_at)),
          p.reversed ? "Dibalik · " + esc(p.reversal_reason) : "Tercatat",
          p.reversed
            ? ""
            : button("Balikkan", "payment.reverse", i.id + "|" + p.id),
        ]),
      )}<div class="actions">${i.status === "issued" ? link("Cetak invoice", "/print/invoice/" + id) + " · " + link("Ekspor Excel", "/api/invoice/" + id + ".xlsx") : ""}${i.status !== "cancelled" ? button("Batalkan invoice", "invoice.cancel", id) : ""}</div>`,
    );
  }
  if (name === "report.print") return window.print();
  if (name === "report.archive") {
    await mutate(name, reportFilters);
    return notify("Snapshot laporan diarsipkan.");
  }
  if (name === "archive.detail") {
    const a = s.archives.find((x) => x.id === id);
    openDialog(
      "Arsip " + date(a.created_at),
      table(
        ["Resi", "Tanggal", "Penjualan", "Status"],
        a.rows.map((r) => [
          esc(r.number),
          esc(r.date),
          r.revenue === undefined ? "—" : fmt(r.revenue),
          badge(r.status),
        ]),
      ),
    );
    return;
  }
  if (name === "master.new") return masterForm(id);
  if (name === "master.edit") {
    const [kind, mid] = id.split("|");
    return masterForm(kind, mid);
  }
  if (name === "account.new" || name === "account.edit") return accountForm(id);
  if (name === "audit.view") {
    const data = await api("/api/audit");
    openDialog(
      "Riwayat audit",
      table(
        ["Waktu", "Tindakan / pelaku", "Perubahan"],
        data.events.map((x) => [
          esc(date(x.at)),
          esc(x.action) + "<small>" + esc(x.actor) + "</small>",
          `<details><summary>${esc(x.entity_id)}</summary><pre>${esc(JSON.stringify({ input: x.payload, sebelum: x.before, sesudah: x.after }, null, 2))}</pre></details>`,
        ]),
      ),
    );
    return;
  }
  if (name === "permissions.edit") {
    const roles = [
      "counter",
      "warehouse",
      "driver",
      "finance",
      "auditor",
      "partner",
    ];
    const operations = [
      "sales",
      "cancel",
      "trip",
      "receipt",
      "pod",
      "report",
      "soa",
      "invoice",
      "reports",
      "financial",
    ];
    return form("Template izin peran", "permissions.save", [
      fields.select(
        "role",
        "Peran",
        roles.map((r) => [r, label(r)]),
      ),
      {
        name: "operations",
        title: "Izin (cakupan cabang tetap diperiksa)",
        type: "checks",
        wide: true,
        options: operations.map((x) => [x, x]),
      },
    ]);
  }
}
document.addEventListener("click", async (e) => {
  const nav = e.target.closest("[data-page]");
  if (nav) {
    page = nav.dataset.page;
    render();
    if (page === "reports") {
      try {
        const d = await api(
          "/api/reports?" + new URLSearchParams(reportFilters),
        );
        reportData = d.rows;
        render();
      } catch (err) {
        notify(err.message);
      }
    }
    return;
  }
  const b = e.target.closest("[data-action]");
  if (b)
    try {
      await action(b.dataset.action, b.dataset.id);
    } catch (err) {
      notify(err.message);
    }
});
document.addEventListener("input", (e) => {
  if (e.target.id === "search") {
    query = e.target.value;
    $("#salesRows").innerHTML = shipmentsTable(
      state().shipments.filter((s) =>
        JSON.stringify([s.number, s.receiver, s.sender.name])
          .toLowerCase()
          .includes(query.toLowerCase()),
      ),
    );
  }
});
document.addEventListener("change", (e) => {
  if (e.target.id === "followupHours") renderFollowups();
});
document.addEventListener("submit", async (e) => {
  if (e.target.id === "reportFilters") {
    e.preventDefault();
    reportFilters = Object.fromEntries(new FormData(e.target));
    try {
      const d = await api("/api/reports?" + new URLSearchParams(reportFilters));
      reportData = d.rows;
      render();
    } catch (err) {
      notify(err.message);
    }
  }
});
$("#closeDialog").onclick = () => $("#dialog").close();
$("#refresh").onclick = () => reload().catch((e) => notify(e.message));
$("#logout").onclick = async () => {
  try {
    await api("/api/logout", { method: "POST" });
  } finally {
    session = null;
    location.reload();
  }
};
$("#loginForm").onsubmit = async (e) => {
  e.preventDefault();
  const formEl = e.currentTarget;
  const b = formEl.querySelector("button");
  b.disabled = true;
  $("#loginError").textContent = "";
  try {
    const f = new FormData(formEl);
    session = await api("/api/login", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(f)),
    });
    formEl.reset();
    await reload();
  } catch (err) {
    $("#loginError").textContent = err.message;
  } finally {
    b.disabled = false;
  }
};
function connectivity() {
  $("#offline").hidden = navigator.onLine;
}
window.addEventListener("online", connectivity);
window.addEventListener("offline", connectivity);
connectivity();
if ("serviceWorker" in navigator)
  navigator.serviceWorker.register("./sw.js").catch(() => {});
let installation;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault();
  installation = e;
  $("#install").hidden = false;
});
$("#install").onclick = async () => {
  if (installation) {
    installation.prompt();
    await installation.userChoice;
    installation = null;
    $("#install").hidden = true;
  }
};
reload().catch((e) => {
  if (e.message !== "Silakan masuk kembali.")
    $("#loginError").textContent = e.message;
});

document.addEventListener("input", (e) => {
  if (e.target.dataset.filterSelect) {
    const select = $("#actionForm").elements[e.target.dataset.filterSelect];
    for (const option of select.options)
      option.hidden =
        Boolean(option.value) &&
        !option.textContent
          .toLowerCase()
          .includes(e.target.value.toLowerCase());
  }
});
