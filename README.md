# GIS Produksi Kota Ternate

Aplikasi web Flask untuk menampilkan peta sebaran produksi perikanan dan pertanian di Kota Ternate. Data ditampilkan per kecamatan menggunakan peta Leaflet, polygon wilayah, marker lokasi, filter jenis produksi, dan cluster K-Means.

## Fitur

- Peta polygon kecamatan dan marker lokasi produksi.
- Filter zona perikanan dan pertanian.
- Ringkasan produksi per kecamatan.
- Data perikanan, tanaman pangan, dan hortikultura berdasarkan tahun terbaru yang tersedia.
- Pengajuan data produksi oleh pengguna.
- Verifikasi atau penolakan data oleh admin.
- Admin perikanan hanya dapat memverifikasi data perikanan.
- Admin pertanian hanya dapat memverifikasi data pertanian.
- Data terverifikasi menggantikan ringkasan impor untuk jenis produksi yang sama.
- Data pending atau rejected tidak memengaruhi ringkasan.
- Importer Excel idempoten dan tidak mengubah database jika file sumber tidak ditemukan.
- Marker perikanan aktif saat ini hanya Perikanan Dufa-Dufa di Ternate Utara.

## Struktur File

- `app.py`: server Flask, autentikasi, API dataset, pengajuan, dan verifikasi.
- `schema.sql`: struktur dan data awal database MySQL.
- `import_crop_data.py`: impor tanaman pangan dan hortikultura.
- `import_fish_data.py`: impor laporan perikanan XLSX yang memiliki pasangan PDF.
- `import_public_boundaries.py`: impor batas kecamatan dari arsip SHP.
- `resolve_zone_overlaps.py`: memperbaiki area tumpang tindih polygon.
- `templates/`: halaman dashboard dan login.
- `static/`: JavaScript peta dan CSS.

## Teknologi dan Package

- Python 3.10 atau lebih baru
- Flask
- mysql-connector-python
- openpyxl
- pyshp (`shapefile`)
- MySQL atau MariaDB
- Leaflet 1.9.4 dari CDN
- OpenStreetMap atau basemap satelit Esri dari sisi frontend

Install package Python:

```powershell
python -m pip install Flask mysql-connector-python openpyxl pyshp
```

## Menyiapkan Database

1. Pastikan MySQL berjalan.
2. Jalankan `schema.sql` melalui phpMyAdmin atau MySQL client.
3. Untuk memasang polygon wilayah, pastikan arsip SHP tersedia lalu jalankan:

```powershell
python import_public_boundaries.py
```

4. Untuk mengimpor data pertanian:

```powershell
python import_crop_data.py
```

5. Untuk mengimpor data perikanan:

```powershell
python import_fish_data.py
```

Importer menggunakan file yang berada di folder proyek. Jika file Excel tidak ada, proses impor dibatalkan dan database tidak diubah. File laporan perikanan hanya diproses jika file XLSX memiliki file PDF dengan nama dasar yang sama.

## Menjalankan Aplikasi

```powershell
python app.py
```

Buka `http://127.0.0.1:5000`.

## Akun Demo

| Peran | Username | Password |
|---|---|---|
| Admin pertanian | `admin_pertanian` | `admin123` |
| Admin perikanan | `admin_perikanan` | `admin123` |
| Pengguna usaha | `user` | `user123` |

Akun demo digunakan untuk pengujian lokal. Ganti password atau akun tersebut sebelum aplikasi digunakan di lingkungan produksi.

Koneksi database dapat diatur melalui environment variable berikut:

- `MYSQL_HOST`, default `127.0.0.1`
- `MYSQL_PORT`, default `3306`
- `MYSQL_USER`, default `root`
- `MYSQL_PASSWORD`, default kosong
- `MYSQL_DATABASE`, default `gis_ternate`
- `FLASK_SECRET_KEY`, disarankan diisi pada lingkungan produksi

## Alur Data

Data impor disimpan pada tabel `fish_production`, `crop_production`, dan `horticulture_production`. Endpoint `/api/dataset` memilih tahun maksimum dari tabel rincian tersebut.

Pengajuan pengguna masuk ke `production_records` dengan status `pending`. Admin hanya dapat memproses data sesuai bidangnya. Setelah berstatus `verified`, nilai tersebut menjadi ringkasan aktif untuk jenis produksi di kecamatan terkait. Status `rejected` tidak digunakan dalam ringkasan.

## Catatan Keamanan

Password disimpan sebagai hash. Jangan menaruh password produksi di dalam `schema.sql`; ganti akun awal dan isi `MYSQL_PASSWORD` melalui environment variable sebelum deployment.
