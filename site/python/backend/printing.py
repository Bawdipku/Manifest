import base64, io, json
from html import escape
from pathlib import Path
from barcode import Code128
from barcode.writer import SVGWriter
from .domain import *


def e(v):
    return escape(str(v or ""))


def rp(v):
    return "Rp " + format(int(v), ",").replace(",", ".")


def render_document(u, state, kind, id):
    title = ""
    body = ""
    copies = []

    def name(id):
        return item(state["masters"]["branches"], id)["name"]

    if kind == "shipment":
        s = item(state["shipments"], id)
        require(
            shipment_visible(u, s, state) and not external(u),
            "Akses cetak BKC ditolak.",
            403,
        )
        require(
            finance_visible(u, s, state),
            "Cetak BKC memerlukan akses nilai transaksi pada cabang asal/tujuan.",
            403,
        )
        require(s["number"], "Draft belum memiliki nomor BKC.")
        title = "BKC " + s["number"]
        buffer = io.BytesIO()
        Code128(s["number"], writer=SVGWriter()).write(
            buffer,
            options={
                "module_width": 0.25,
                "module_height": 12,
                "font_size": 10,
                "quiet_zone": 3,
            },
        )
        barcode = base64.b64encode(buffer.getvalue()).decode()
        terms = json.loads((Path(__file__).parent / "bkc-terms.json").read_text())
        copies = [
            "Lembar Pengirim",
            "Lembar Cabang Pengirim",
            "POD / Billing",
            "Lembar Cabang Tujuan",
            "Arsip Finance",
        ]
        for copy_ in copies:
            total = s["values"]["cash"] + s["values"]["credit"] + s["values"]["collect"]
            body += (
                f'<section class="copy"><header><div><h1>Bukti Kirim Cargo</h1><p>{e(copy_)}</p></div><div><strong>{e(s["number"])}</strong><p>{e(s["ship_date"])}</p></div></header><img class="barcode" alt="Barcode Code 128 {e(s["number"])}" src="data:image/svg+xml;base64,{barcode}"><p>{e(name(s["origin"]))} → {e(s["destination"])} · Cabang penerima: {e(name(s["final_branch"]))}</p><div class="grid"><div><h3>Pengirim</h3>{e(s["sender"]["name"])}<p>{e(s["sender"]["address"])}</p>{e(s["sender"]["contact"])}</div><div><h3>Penerima</h3>{e(s["receiver"])}<p>{e(s["address"])}</p>{e(s["contact"])}</div></div><p>{e(s["packages"])} koli · {e(s["weight"])} kg · {e(s["description"])}</p><p>Referensi: {e(s["reference"])}</p><table><tr><th>Tunai</th><th>Kredit</th><th>Tagih tujuan</th><th>Biaya penerus</th><th>Total penjualan</th></tr><tr>'
                + "".join(
                    "<td>" + rp(s["values"][k]) + "</td>"
                    for k in ("cash", "credit", "collect", "forwarding")
                )
                + f"<td>{rp(total)}</td></tr></table>"
            )
            if copy_ == "Lembar Cabang Pengirim":
                body += (
                    '<h3>Syarat dan Ketentuan</h3><div class="terms">'
                    + "".join("<p>" + e(x) + "</p>" for x in terms["preamble"])
                    + "".join(
                        "<h4>"
                        + e(x["title"])
                        + "</h4>"
                        + "".join("<p>" + e(y) + "</p>" for y in x["items"])
                        for x in terms["sections"]
                    )
                    + '</div><p class="statement">'
                    + e(terms["statement"])
                    + "</p>"
                )
            body += '<div class="sign"><p>Nama pengirim / utusan: __________________<br>Tanggal / jam: __________________</p><p>Tanda tangan dan cap perusahaan<br><br><br>__________________</p><p>Penerima / petugas<br><br><br>__________________</p></div></section>'
    elif kind == "trip":
        t = item(state["trips"], id)
        require(
            not external(u) and (branch(u, t["origin"]) or branch(u, t["destination"])),
            "Akses surat jalan ditolak.",
            403,
        )
        title = "Manifest " + id
        body = f'<h1>Surat Jalan / Manifest</h1><h2>{e(id)}</h2><p>{e(name(t["origin"]))} → {e(name(t["destination"]))} · {e(t["type"])}</p><p>{e(t["driver"])} · {e(t["vehicle"])} · {e(t.get("departed_at",t["planned_date"]))}</p><table><tr><th>Resi</th><th>Tujuan akhir</th><th>Penerima</th><th>Koli</th><th>Kg</th></tr>'
        for s in trip_ships(state, t):
            body += (
                "<tr>"
                + "".join(
                    "<td>" + e(v) + "</td>"
                    for v in (
                        s["number"],
                        s["destination"],
                        s["receiver"],
                        s["packages"],
                        s["weight"],
                    )
                )
                + "</tr>"
            )
        body += '</table><div class="sign"><p>Pengirim<br><br><br>____________</p><p>Pengemudi / vendor<br><br><br>____________</p><p>Penerima cabang<br><br><br>____________</p></div>'
    elif kind == "invoice":
        permit(u, state, "invoice")
        i = item(state["invoices"], id)
        at_branch(u, i["origin"])
        require(i["status"] == "issued", "Invoice belum diterbitkan.")
        title = id
        body = (
            f'<h1>Invoice {e(id)}</h1><p>{e(i["customer_snapshot"]["name"])}</p><p>{e(i["customer_snapshot"].get("address",""))}</p><p>{e(i["issued_at"])}</p><table><tr><th>Resi</th><th>Kredit</th></tr>'
            + "".join(
                "<tr><td>"
                + e(l["number"])
                + "</td><td>"
                + rp(l["value"])
                + "</td></tr>"
                for l in i["lines"]
            )
            + "</table><h3>Total "
            + rp(i["total"])
            + "</h3><p>Saldo "
            + rp(
                i["total"]
                - sum(x["value"] for x in i["payments"] if not x.get("reversed"))
            )
            + "</p>"
        )
    else:
        raise Problem("Dokumen tidak ditemukan.", 404)
    return (
        '<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'
        + e(title)
        + '</title><link rel="stylesheet" href="/print.css"></head><body><p class="help">Gunakan menu Cetak browser · A4 · skala 100%. Validasi cetak fisik dan scanner sebelum penggunaan lapangan.</p>'
        + body
        + "</body></html>"
    )
