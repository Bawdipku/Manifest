# PRD — Manifest & SOA

**Versi produk:** 1.6
**Tanggal dokumen:** 7 Oktober 2026
**Status:** Dokumentasi fitur yang sudah dibangun
**Situs:** https://manifest-soa.adrian-120130023.chatgpt.site

## 1. Ringkasan produk

Manifest & SOA adalah aplikasi operasional cargo untuk mencatat penjualan pengiriman, membuat resi berbarcode, menyusun manifest perjalanan, memantau perpindahan barang antarcabang, mencatat Proof of Delivery (POD), membandingkan SOA sementara dengan SOA asli, mengelola pengembalian dokumen POD, serta mencatat tagihan pelanggan.

Aplikasi mendukung pengiriman langsung dan pengiriman melalui beberapa tahap. Satu resi dapat melewati trip asal, hub transit, dan cabang tujuan tanpa dibuat sebagai penjualan baru pada setiap tahap.

## 2. Tujuan

1. Memberikan satu identitas resi yang konsisten dari penjualan sampai penyelesaian dokumen.
2. Mengetahui trip, cabang, dan pihak yang bertanggung jawab atas barang pada setiap tahap.
3. Memisahkan penerimaan barang di cabang dari POD penerima akhir.
4. Menjaga SOA sementara sebagai pembanding yang tidak tertimpa oleh SOA asli.
5. Memungkinkan laporan agen atau vendor melalui ponsel maupun input bantuan admin, dengan verifikasi sebelum mengubah status resmi.
6. Menampilkan penjualan, pengiriman, rekonsiliasi, pembatalan, dan tagihan tanpa menghitung transaksi yang sama dua kali.

## 3. Pengguna dan hak akses

| Peran | Tanggung jawab utama |
|---|---|
| Administrator sistem | Mengelola akun, master, kebijakan, pengawasan, penugasan mitra, dan verifikasi laporan mitra |
| Counter / CS | Mencatat penjualan serta membuat dan mendaftarkan resi |
| Gudang / operasional | Mengelola trip, grouping, manifest, keberangkatan, dan serah terima sesuai cakupan cabang |
| Kurir / pengemudi | Melihat kiriman yang ditugaskan dan menjalankan tindakan pengantaran yang diizinkan |
| Finance | Memasukkan SOA asli, meninjau rekonsiliasi, mengelola invoice dan pembayaran sesuai cabang |
| Manajemen / auditor | Melihat informasi dan laporan sesuai izin, tanpa mengubah transaksi |
| Mitra / agen lapangan | Melihat kiriman yang ditugaskan dan mengirim laporan serta bukti melalui portal ponsel |

Administrator dapat mengatur template izin dan cakupan cabang. Aplikasi memeriksa izin di sisi server, termasuk saat membuka dokumen. Akun mitra hanya menerima data kiriman yang ditugaskan; data keuangan, master pelanggan, dan akun internal tidak tersedia di portalnya.

Akses ke situs dan akun aplikasi adalah dua hal terpisah. Seseorang memerlukan akses situs yang sesuai serta akun aplikasi yang aktif untuk bekerja.

## 4. Istilah operasional

- **Resi/BKC:** Identitas satu transaksi pengiriman. Contoh format: `PKU-261003-000001`.
- **Barcode:** Representasi Code 128 dari nomor resi. Scanner barcode yang mengetik nomor dan Enter dapat dipakai untuk pencarian.
- **Trip:** Satu perjalanan kendaraan atau vendor dari cabang asal tahap menuju tujuan tahap.
- **Manifest:** Daftar resi yang menjadi muatan suatu trip.
- **DEST:** Kota tujuan akhir yang dipakai untuk grouping SOA awal.
- **P2P (Port to Port):** Tahap pengiriman menuju cabang penerima. Tahap dapat ditandai sebagai transit/hub atau cabang tujuan akhir.
- **P2D (Port to Door):** Tahap pengantaran langsung kepada penerima akhir.
- **SOA sementara:** Nilai dan kebijakan yang disimpan saat grouping awal serta dikonfirmasi sebelum trip pertama berangkat.
- **SOA asli:** Nilai aktual yang dicatat setelah POD untuk dibandingkan dengan SOA sementara.
- **POD:** Bukti bahwa satu resi diterima oleh penerima akhir.
- **Pengembalian POD:** Pergerakan dokumen POD fisik kembali ke cabang asal.

## 5. Alur utama

1. Counter memilih cabang asal, kota tujuan, cabang penerima akhir, dan pelanggan bila terdaftar.
2. Counter mengisi penerima, alamat, muatan, serta komponen penjualan, lalu mendaftarkan resi.
3. Sistem memberikan nomor resi unik dan menyediakan BKC dengan barcode.
4. Operasional membuat trip dan memilih jenis P2P/P2D serta pelaksana internal/vendor.
5. Resi dikelompokkan berdasarkan trip dan DEST; petugas mengonfirmasi SOA sementara.
6. Operasional mencatat waktu keberangkatan sebenarnya. Trip menyimpan waktu kejadian dan waktu input secara terpisah.
7. Pada P2P, cabang penerima mencatat resi yang benar-benar tiba, secara individual atau sebagian dari satu trip.
8. Jika cabang penerima adalah hub, petugas membuat trip berikutnya dan memasukkan resi yang sudah diterima ke manifest lanjutan.
9. Pada tahap akhir, pengantaran menghasilkan POD per resi.
10. Finance memasukkan SOA asli, membandingkannya dengan snapshot sementara, dan menyelesaikan selisih sesuai izin.
11. Dokumen POD fisik dikirim kembali dan dikonfirmasi diterima oleh cabang asal.

Penerimaan cabang pada langkah 7 tidak berarti penerima akhir telah menerima barang. POD dan pengembalian dokumen fisik juga merupakan dua peristiwa yang berbeda.

## 6. Persyaratan fungsional

### 6.1 Master dan akun

- Administrator dapat mengelola cabang, kota, pegawai, pelanggan, armada, tarif referensi, produk, satuan, dan vendor.
- Data pelanggan dan armada dapat dicari dan dipilih dari daftar.
- Pemilihan pelanggan mengisi data pengirim; pemilihan armada mengisi nomor polisi.
- Data pengirim yang digunakan transaksi disimpan sebagai snapshot agar perubahan master kemudian tidak diam-diam mengubah transaksi lama.
- Cabang mempunyai kode kantor, kode kota, prefix barcode, dan relasi pengendali bila diperlukan.
- Administrator dapat membuat akun, menentukan peran, cabang, cakupan tambahan, serta penugasan vendor untuk akun mitra.

### 6.2 Penjualan dan resi

- Penjualan mempunyai status draft, terdaftar, atau dibatalkan.
- Resi menyimpan pengirim, penerima, alamat, kontak, asal, tujuan, cabang penerima, koli, berat, tanggal kirim, dan komponen nilai penjualan.
- Komponen penjualan yang dicatat adalah tunai, kredit, tagih tujuan, dan biaya penerus.
- Nomor resi harus unik. Nomor yang telah diberikan tetap digunakan pada seluruh tahap perjalanan.
- BKC dapat dicetak dalam salinan pengirim, kantor asal, POD/billing, kantor tujuan, dan arsip finance sesuai izin akun.
- Pembatalan menyimpan alasan, pelaku, waktu, dan riwayat transaksi. Pembatalan yang terkait SOA atau laporan keuangan mempunyai pembatasan izin tambahan.

### 6.3 Trip dan manifest

- Trip menyimpan cabang asal tahap, jenis P2P/P2D, pelaksana internal/vendor, tanggal, driver, armada atau nomor polisi, serta tujuan cabang untuk P2P.
- Trip vendor menyimpan identitas vendor dan referensi surat jalan. Serah terima kepada vendor dicatat sebelum penerimaan lanjutan atau POD.
- Trip P2P dapat ditandai **transit/hub** atau **cabang tujuan akhir**.
- Trip transit dapat membawa resi dari beberapa kota tujuan akhir. SOA awal tetap dikelompokkan menurut DEST masing-masing.
- Trip tujuan akhir P2P hanya menerima resi dengan cabang tujuan akhir yang cocok.
- Surat jalan menampilkan muatan trip dan ruang tanda tangan.
- Manifest lama tetap dapat dilihat setelah sebuah resi diteruskan ke trip berikutnya.

### 6.4 Manifest lanjutan

- Resi hanya dapat diteruskan setelah tercatat diterima pada trip P2P sebelumnya di cabang asal trip baru.
- Petugas dapat mencari atau memasukkan nomor resi menggunakan scanner keyboard untuk memilih muatan lanjutan.
- Satu proses penambahan menerima paling banyak 200 resi unik.
- Resi yang sedang menunggu laporan mitra diverifikasi tidak dapat diteruskan.
- Resi yang dibatalkan, sudah POD, belum diterima, salah cabang, atau sudah terikat trip lain tidak dapat ditambahkan.
- Penugasan ke draft trip dapat dibatalkan dengan alasan; resi kembali ke posisi operasional tahap sebelumnya.
- Setelah trip diberangkatkan, muatan tidak dapat dikeluarkan melalui tindakan penghapusan draft.
- Waktu keberangkatan tahap baru tidak boleh lebih awal daripada waktu penerimaan tahap sebelumnya.
- Manifest lanjutan mempertahankan nomor resi, SOA awal, snapshot kebijakan, dan tanggal keberangkatan pertama yang digunakan laporan keuangan.
- Setiap tahap mencatat trip, rute, pelaksana, waktu berangkat, dan penerimaan individual dalam riwayat resi.

### 6.5 Status, laporan lapangan, dan POD

- Status operasional mencakup menunggu berangkat, diberangkatkan, dalam perjalanan, tiba, diantar, dan POD tercatat.
- Penerimaan cabang P2P dapat dilakukan untuk sebagian resi dalam satu trip, dengan petugas penerima, waktu, kondisi, dan catatan.
- Tahap transit tidak dapat menghasilkan POD penerima akhir.
- POD dicatat per resi dengan nama penerima dan waktu penerimaan; aturan bukti atau alasan pengecualian mengikuti jalur pencatatan yang digunakan.
- Pada perjalanan beberapa tahap, POD tidak boleh mendahului keberangkatan atau serah terima vendor pada tahap terakhir.
- Admin atau staf berizin dapat memasukkan laporan lapangan yang diterima melalui WhatsApp, telepon, email, atau tatap muka.
- Mitra dapat mengirim laporan langsung melalui portal ponsel untuk resi yang ditugaskan.
- Jenis laporan lapangan: tiba di tujuan tahap, diterima penerima akhir, dan kendala pengiriman.
- Laporan menyimpan pelapor, sumber, kontak, waktu kejadian, waktu input, dan pencatat.
- Laporan mitra berstatus menunggu hingga administrator menyetujui atau menolaknya. Laporan menunggu tidak langsung mengubah status resmi.
- Bukti laporan dapat berupa JPEG, PNG, atau PDF, maksimal 10 MB per berkas dan lima berkas per laporan.
- Persetujuan laporan POD memerlukan bukti dan menghasilkan POD resmi, tetapi tidak otomatis membuat SOA asli atau menandai dokumen fisik telah kembali.
- Daftar tindak lanjut menampilkan kendala terbuka dan kiriman tanpa laporan terbaru dengan ambang 24, 48, atau 72 jam.

### 6.6 SOA dan rekonsiliasi

- SOA sementara dibuat per pasangan trip dan DEST pada grouping awal.
- Konfirmasi membuat snapshot nilai, kebijakan, dan versi; revisi versi terkonfirmasi memerlukan alasan.
- Trip pertama hanya boleh berangkat setelah resi aktif mempunyai SOA sementara terkonfirmasi.
- Trip lanjutan menggunakan snapshot yang sudah ada, tanpa membuat SOA atau penjualan baru.
- SOA asli dapat dibuat setelah POD, lalu dibandingkan per resi terhadap SOA sementara.
- Hasil perbandingan menunjukkan sesuai, selisih, atau selisih yang telah diselesaikan.
- Riwayat versi, alasan revisi, dan keputusan peninjauan tetap tersedia.
- SOA sementara yang memakai kebijakan provisional ditandai dan tidak dapat difinalisasi sebagai rekonsiliasi sesuai kebijakan yang belum disetujui.

### 6.7 Pengembalian dokumen POD

- Status dokumen membedakan menunggu POD, menunggu kembali, dalam pengembalian, diterima di asal, dan dokumen bermasalah.
- Setelah POD, petugas dapat membuat batch pengembalian dokumen dengan referensi.
- Cabang asal mengonfirmasi penerimaan fisik dokumen.
- Status barang terkirim dan status dokumen fisik ditampilkan secara terpisah.

### 6.8 Invoice pelanggan

- Finance dapat membuat draft invoice, memilih resi, menerbitkan invoice, mencetak rincian, dan mengekspor data.
- Dasar tagihan invoice versi ini adalah **komponen kredit yang tercatat** pada penjualan.
- Satu resi hanya dapat diklaim oleh satu invoice aktif.
- Nilai dan identitas pelanggan dibekukan saat invoice diterbitkan.
- POD tidak menjadi syarat penerbitan invoice.
- Pembayaran dapat dicatat sebagian atau penuh. Sistem menghitung saldo dan menolak kelebihan pembayaran serta referensi ganda pada invoice yang sama.
- Koreksi pencatatan pembayaran menggunakan pembalikan dengan alasan; riwayat aslinya tetap ada.
- Invoice tidak menambah omzet laporan penjualan untuk kedua kalinya.

### 6.9 Laporan

- Laporan menyediakan tampilan penjualan tercatat, kiriman diberangkatkan, rekonsiliasi, pembatalan, penyelesaian keuangan, serta status dokumen POD.
- Draft penjualan tidak masuk total penjualan terdaftar.
- Kiriman diberangkatkan dan direkonsiliasi adalah cakupan dari penjualan yang sama, bukan pendapatan tambahan.
- Pembatalan tetap terlihat dalam riwayat, tetapi dikeluarkan dari total aktif sesuai aturan laporan.
- Filter tanggal mengikuti waktu Asia/Jakarta dan mendukung cabang, status, serta pencarian resi.
- Laporan dapat dicetak dan diekspor ke Excel sesuai izin.
- Admin atau finance dapat mengarsipkan snapshot laporan bertanggal sesuai cakupan cabang.

## 7. Aturan akses dan integritas

1. Setiap tindakan harus memeriksa peran dan cabang di server.
2. Kurir dan mitra hanya melihat resi yang sedang ditugaskan kepada mereka.
3. Penugasan ulang mitra menghapus akses mitra lama ke resi dan bukti yang dibatasi penugasan.
4. Cabang transit dapat melihat riwayat operasional resi yang melewatinya tanpa memperoleh angka SOA atau laporan keuangan hanya karena menjadi titik transit.
5. Berkas POD dan bukti laporan diakses melalui permintaan terautentikasi, bukan tautan penyimpanan publik.
6. Tindakan penting mempunyai riwayat pelaku, waktu, dan perubahan.
7. Penyimpanan tindakan memakai pemeriksaan revisi serta kunci permintaan untuk menghindari perubahan bersamaan dan pengulangan penyimpanan.
8. Urutan waktu keberangkatan, serah terima, penerimaan, dan POD harus konsisten dengan aturan setiap tahap.

## 8. Kriteria penerimaan

- Satu resi dapat melewati sedikitnya tiga tahap: asal → hub → cabang tujuan → penerima.
- Cabang hub hanya dapat meneruskan resi yang benar-benar diterimanya.
- Penerimaan sebagian tidak otomatis meneruskan seluruh muatan trip.
- Riwayat tiap manifest tetap terlihat setelah resi pindah trip.
- Nomor resi, SOA awal, dan tanggal keberangkatan pertama tidak berubah akibat perjalanan lanjutan.
- Tahap transit tidak dapat membuat POD.
- Resi yang sama tidak dapat berada dalam dua trip aktif sekaligus.
- Mitra lama tidak dapat membuka resi yang sudah ditugaskan ulang.
- Persetujuan laporan POD mitra memerlukan bukti dan hak administrator.
- Laporan keuangan menghitung setiap penjualan satu kali meskipun resi melewati beberapa trip.
- Penerimaan POD fisik di cabang asal tetap merupakan tindakan tersendiri.

## 9. Batasan versi saat ini

- Pemecahan satu resi menjadi beberapa kendaraan berdasarkan sebagian koli belum didukung.
- Belum ada saldo stok gudang atau mesin inventaris per lokasi.
- Belum ada perhitungan ongkos dan penyelesaian keuangan per tahap perjalanan atau per vendor.
- Tarif master tersedia sebagai referensi; perhitungan tarif otomatis lengkap berdasarkan berat volume dan layanan belum menjadi alur utama.
- Belum ada integrasi WhatsApp otomatis, notifikasi keluar, sinkronisasi offline, atau tracking publik pelanggan.
- Belum ada pemindaian barcode melalui kamera. Scanner barcode eksternal yang bertindak sebagai keyboard dapat digunakan.
- QR, voucher, manajemen blangko, peramalan permintaan, dan pusat bantuan pengguna tidak termasuk cakupan yang dipilih.
- Pengujian perangkat ponsel, scanner fisik, dan cetak fisik masih diperlukan sebelum menetapkan SOP produksi lapangan.

## 10. Arah pengembangan berikutnya

Prioritas berikutnya perlu ditentukan dari penggunaan nyata di cabang. Kandidat yang sudah teridentifikasi adalah tarif otomatis dan berat volume; percobaan pengantaran, gagal antar, pengiriman ulang dan retur; tracking pelanggan; serta pengujian kapasitas dan pemulihan data. Fitur pada bagian ini adalah rencana, bukan klaim kemampuan versi 1.6.
