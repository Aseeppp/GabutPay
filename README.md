# GabutPay: Solusi Simulasi E-Wallet dan Payment Gateway

> **⚠️ PERINGATAN PENTING (DISCLAIMER):**
> Proyek ini dibuat sepenuhnya untuk **tujuan pembelajaran, demonstrasi teknis, dan portofolio**. Seluruh transaksi, saldo, dan aliran dana di dalam aplikasi ini adalah **SIMULASI** dan tidak menggunakan atau melibatkan uang asli (fiat) maupun aset kripto. Penulis tidak bertanggung jawab atas penyalahgunaan aplikasi ini di luar tujuan pembelajaran.

GabutPay adalah platform simulasi keuangan berbasis web yang dirancang menggunakan kerangka kerja **Python Flask**. Proyek ini berfungsi ganda sebagai dompet digital (*e-wallet*) bagi pengguna umum dan sebagai gerbang pembayaran (*payment gateway*) bagi pengembang atau mitra bisnis. 

Tujuan utama proyek ini adalah untuk mendemonstrasikan implementasi sistem transaksi keuangan yang aman, menangani integrasi API antar sistem, serta mengelola integritas data dalam lingkungan yang terdistribusi.

---

## 1. Konsep dan Cara Kerja

GabutPay beroperasi dengan membagi peran pengguna menjadi tiga kategori utama:

1.  **Pengguna Reguler (E-Wallet):** Pengguna dapat mengelola saldo virtual, melakukan transfer antar pengguna menggunakan PIN, membayar tagihan melalui QR Code, serta mengelola tagihan bersama (*Split Bill*).
2.  **Merchant (Payment Gateway):** Setiap pengguna dapat mengaktifkan fitur Merchant dengan membuat API Key. Merchant dapat mengintegrasikan GabutPay ke aplikasi eksternal untuk menerima pembayaran melalui link pembayaran atau QR Code dinamis.
3.  **Partner (Inbound Support):** Pengguna dengan status khusus (*Partner*) yang memiliki akses ke Inbound API. Fitur ini memungkinkan mitra untuk menambahkan saldo ke akun pengguna GabutPay secara otomatis melalui integrasi server-to-server.

---

## 2. Fitur Utama Sistem

### A. Keamanan Transaksi
*   **HMAC-SHA256 Signature:** Menjamin integritas permintaan API. Setiap *request* harus menyertakan tanda tangan digital yang diverifikasi di sisi server.
*   **IP Whitelisting:** Membatasi akses API Key Partner hanya dari alamat IP yang telah didaftarkan.
*   **Idempotency Key:** Menggunakan `external_id` pada transaksi inbound untuk mencegah duplikasi penambahan saldo jika terjadi pengiriman ulang permintaan API.
*   **Row-Level Locking:** Mengimplementasikan mekanisme penguncian basis data (`with_for_update`) untuk mencegah kesalahan perhitungan saldo akibat transaksi yang bersamaan (*race condition*).

### B. Fungsionalitas Pengguna
*   **Transfer & Split Bill:** Pengiriman dana instan antar pengguna dan sistem manajemen patungan otomatis.
*   **Dynamic QR Code:** Pemindaian dan pembuatan QR Code standar untuk proses pembayaran yang cepat.
*   **Notifikasi Real-time:** Integrasi *Web Push Notification* untuk menginformasikan setiap aktivitas transaksi kepada pengguna.

### C. Integrasi Developer
*   **Webhooks:** Pengiriman notifikasi otomatis dari server GabutPay ke server Merchant ketika status pembayaran berubah menjadi lunas (*PAID*).
*   **Dokumentasi API Internal:** Tersedia panduan teknis lengkap di rute `/docs` yang mencakup contoh kode dalam berbagai bahasa pemrograman.

---

## 3. Persyaratan Sistem

Sebelum melakukan instalasi, pastikan sistem Anda memenuhi kriteria berikut:
*   **Python:** Versi 3.8 atau lebih tinggi.
*   **Database:** PostgreSQL (Direkomendasikan) atau SQLite untuk keperluan pengembangan.
*   **Email Server:** Akun SMTP (seperti Gmail App Password) untuk layanan OTP dan notifikasi.

---

## 4. Panduan Instalasi dan Konfigurasi

### Langkah 1: Persiapan Lingkungan
Unduh repositori dan siapkan lingkungan virtual Python:
```bash
git clone https://github.com/Aseeppp/GabutPay.git
cd GabutPay
python -m venv venv
source venv/bin/activate  # Linux/macOS
# venv\Scripts\activate   # Windows
```

### Langkah 2: Instalasi Dependensi
Instal seluruh pustaka yang diperlukan:
```bash
pip install -r requirements.txt
```

### Langkah 3: Konfigurasi Environment (`.env`)
Buat file bernama `.env` di direktori utama dan lengkapi konfigurasi sesuai contoh berikut:
```ini
# =========================
# APP CONFIG
# =========================
SECRET_KEY='kunci-rahasia-super-aman-jangan-disebar-luaskan-ya'
ENCRYPTION_KEY='kunci_rahasia_super_aman_anda'

# =========================
# DATABASE
# =========================
SQLALCHEMY_DATABASE_URI='sqlite:///gabutpay.db'

# =========================
# EMAIL CONFIG
# =========================
MAIL_SERVER='smtp.gmail.com'
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME='emailanda@gmail.com'
MAIL_PASSWORD='password_aplikasi_anda'
ADMIN_EMAIL='emailanda@gmail.com'

# =========================
# PUSH NOTIFICATION (VAPID)
# =========================
VAPID_PRIVATE_KEY='vapid_private_key'
VAPID_PUBLIC_KEY='vapid_public_key'
```

### Langkah 4: Inisialisasi Basis Data
Jalankan migrasi untuk menyusun struktur tabel di basis data:
```bash
flask db upgrade
```

### Langkah 5: Setup Akun Sistem
Sistem memerlukan satu akun administrator utama untuk mengelola dana dari biaya layanan (*fees*):
```bash
python create_admin.py
```

---

## 5. Cara Penggunaan

### Menjalankan Aplikasi
Gunakan perintah berikut untuk memulai server pengembangan:
```bash
python run.py
```
Aplikasi secara default dapat diakses melalui browser di alamat `http://127.0.0.1:5000`.

### Integrasi Inbound (Untuk Partner)
Untuk menggunakan API Inbound, pastikan Anda telah:
1.  Mendaftarkan API Key di Dashboard Merchant.
2.  Meminta Administrator untuk mengaktifkan status **Partner** pada akun Anda.
3.  Mendaftarkan IP Server Anda pada konfigurasi API Key di panel admin.

Kirimkan permintaan `POST` ke `/api/v1/inbound-transfer` dengan header `X-SIGNATURE` yang valid untuk memproses penambahan saldo pengguna secara otomatis.

---

## 6. Lisensi
Proyek ini didistribusikan di bawah lisensi **MIT**. Anda diizinkan untuk memodifikasi dan mendistribusikan ulang dengan tetap menyertakan atribusi penulis asli.
