# GabutPay: Simulasi E-Wallet & Payment Gateway

GabutPay adalah proyek aplikasi web berbasis Python dan Flask yang menyimulasikan platform finansial dengan dua fungsi utama: sebagai **dompet digital (e-wallet)** untuk pengguna individu dan sebagai **payment gateway** untuk merchant atau developer. Proyek ini dirancang sebagai studi kasus dan portofolio untuk mendemonstrasikan implementasi fitur-fitur finansial dalam lingkungan yang aman dan terkontrol.

Aplikasi ini dibangun dengan fokus pada arsitektur yang modular, praktik keamanan fundamental, dan pengalaman pengguna yang intuitif.

## Konsep Inti

- **Fungsi Ganda**: Pengguna dapat mendaftar, mengelola saldo, dan melakukan transaksi layaknya pengguna e-wallet. Secara bersamaan, setiap pengguna dapat bertindak sebagai *merchant* dengan membuat API Key untuk mengintegrasikan pembayaran pada aplikasi atau situs web eksternal.
- **Simulasi Realistis**: Meskipun seluruh transaksi bersifat simulasi dan tidak melibatkan uang nyata, alur prosesnya dirancang untuk meniru cara kerja sistem pembayaran modern, termasuk penerapan biaya layanan (fees) dan mekanisme transfer dana antar pihak.
- **Keamanan sebagai Prioritas**: Aplikasi ini mengimplementasikan praktik keamanan esensial, seperti hashing untuk kredensial, verifikasi email, otentikasi transaksi dengan PIN, dan proteksi endpoint API menggunakan signature HMAC.
- **API-Driven**: Fungsionalitas payment gateway diekspos melalui REST API yang terdokumentasi, memungkinkan developer untuk berintegrasi secara terprogram.

## Fitur Utama

### Untuk Pengguna (Fungsi E-Wallet)
- **Manajemen Akun**: Registrasi pengguna baru dengan verifikasi One-Time Password (OTP) melalui email, serta proses login yang aman.
- **Manajemen Saldo**: Pengguna memiliki saldo virtual yang dapat digunakan untuk berbagai transaksi. Riwayat semua transaksi tercatat dan dapat diakses.
- **Transfer Dana**: Kemampuan untuk mentransfer saldo ke sesama pengguna GabutPay secara instan, diamankan dengan otentikasi PIN.
- **Pembayaran QR Code**:
    - Membuat permintaan pembayaran dengan menghasilkan QR code dinamis.
    - Memindai QR code menggunakan kamera perangkat atau dari galeri untuk melakukan pembayaran.
- **Tagihan Patungan (Split Bill)**:
    - Membuat sesi tagihan bersama dengan beberapa partisipan.
    - Sistem secara otomatis membagi total tagihan dan mengelola status pembayaran setiap partisipan.
- **Notifikasi Push**: Menerima notifikasi real-time untuk aktivitas penting seperti transfer masuk dan pembayaran berhasil (memerlukan persetujuan pengguna).
- **Sistem Pencapaian (Achievements)**: Mendapatkan lencana (badges) untuk pencapaian tertentu, seperti melakukan transfer pertama atau mencapai streak login.
- **Keamanan Akun**: Fitur untuk mengatur atau mereset PIN keamanan dan password akun melalui tautan yang dikirim ke email.

### Untuk Developer (Fungsi Payment Gateway)
- **Dasbor Merchant**: Halaman khusus untuk mengelola API Key, melihat statistik, dan mengkonfigurasi webhook.
- **Manajemen API Key**: Kemampuan untuk membuat, mereset, dan menghapus API Key. Pembuatan key pertama bersifat gratis, sedangkan key berikutnya dikenakan biaya yang dipotong dari saldo.
- **Integrasi API**:
    - Endpoint RESTful untuk membuat sesi pembayaran (`create-payment`).
    - Mendukung pembuatan **link pembayaran** atau **QR code dinamis** secara on-demand melalui API.
- **Notifikasi Webhook**: Merchant dapat menyediakan URL webhook untuk menerima notifikasi server-to-server (HTTP POST) secara otomatis ketika status pembayaran berubah (misalnya, dari `PENDING` menjadi `PAID`).
- **Dokumentasi API Komprehensif**: Menyediakan panduan teknis yang detail (/docs) mengenai cara otentikasi, daftar endpoint, format request/response, dan contoh kode dalam berbagai bahasa pemrograman (Python, Node.js).

## Arsitektur dan Teknologi

- **Backend**: Python 3, Flask
- **Database**: PostgreSQL (direkomendasikan untuk produksi), SQLite (untuk development). Menggunakan Flask-SQLAlchemy sebagai ORM dan Flask-Migrate untuk manajemen skema.
- **Keamanan**:
    - Hashing: Flask-Bcrypt untuk password dan PIN.
    - Serializer: `itsdangerous` untuk token yang aman (reset password, link pembayaran).
    - Proteksi API: HMAC-SHA256 untuk request signature.
- **Frontend**:
    - Templating: Jinja2.
    - Framework CSS: Bootstrap 5.
    - Interaktivitas: Vanilla JavaScript untuk fitur seperti scanner QR dan notifikasi.
- **Layanan Email**: Flask-Mail untuk pengiriman email transaksional (OTP, notifikasi reset).
- **Deployment**: Proyek ini siap untuk di-deploy pada platform cloud modern seperti Railway, Heroku, atau DigitalOcean.

## Instalasi dan Konfigurasi Lokal

Untuk menjalankan proyek ini di lingkungan development, ikuti langkah-langkah berikut:

#### 1. Prasyarat
- Python 3.8 atau lebih tinggi.
- `pip` dan `venv`.
- Git.

#### 2. Setup Proyek
```bash
# Clone repositori dari GitHub
git clone https://github.com/Aseeppp/GabutPay.git
cd GabutPay

# Buat dan aktifkan virtual environment
python -m venv venv
source venv/bin/activate  # Untuk Linux/macOS
# venv\Scripts\activate  # Untuk Windows

# Install semua dependensi yang dibutuhkan
pip install -r requirements.txt
```

#### 3. Konfigurasi Environment
Buat file `.env` di direktori root proyek. File ini akan menyimpan semua konfigurasi sensitif. Salin konten dari contoh di bawah dan sesuaikan nilainya.

```ini
# Kunci rahasia untuk sesi Flask dan enkripsi. Ganti dengan string acak yang kuat.
SECRET_KEY=ganti_dengan_kunci_rahasia_yang_sangat_aman

# Konfigurasi Database (pilih salah satu)
# Untuk PostgreSQL (rekomendasi)
DATABASE_URL="postgresql://user:password@host:port/dbname"
# Untuk SQLite (development)
# DATABASE_URL="sqlite:///instance/gabutpay.db"

# Konfigurasi Server Email (contoh menggunakan Gmail)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=True
MAIL_USERNAME=alamat.email.anda@gmail.com
MAIL_PASSWORD=password_aplikasi_gmail_anda # Gunakan App Password, bukan password utama

# Alamat email untuk menerima laporan bug
ADMIN_EMAIL=email_admin_anda@example.com

# Konfigurasi VAPID untuk Notifikasi Push (opsional)
# Anda bisa generate kunci ini menggunakan library seperti py-vapid
VAPID_PRIVATE_KEY=kunci_privat_vapid
VAPID_PUBLIC_KEY=kunci_publik_vapid
VAPID_CLAIM_EMAIL=mailto:alamat.email.anda@gmail.com

# Biaya-biaya (dalam sen)
KEY_COST=10000 # Biaya pembuatan API Key (Rp 100.00)
PAYER_FEE_TRANSFER_PERCENT=0.005 # 0.5%
PAYER_FEE_LINK_PERCENT=0.01 # 1%
PAYER_FEE_QR_PERCENT=0.007 # 0.7%
MERCHANT_FEE_PERCENT=0.015 # 1.5%
```

#### 4. Inisialisasi Database
Jalankan perintah berikut untuk membuat skema database berdasarkan model yang ada.

```bash
# Inisialisasi migrasi (hanya dijalankan sekali saat pertama kali)
flask db init

# Buat file migrasi awal
flask db migrate -m "Initial migration"

# Terapkan migrasi ke database
flask db upgrade
```

#### 5. Buat Akun Administrator
Aplikasi memerlukan satu akun sistem (`sistem@gabutpay.com`) untuk menampung dana dari biaya layanan. Buat akun ini menggunakan skrip yang telah disediakan.

```bash
python create_admin.py
```

#### 6. Jalankan Aplikasi
Setelah semua setup selesai, jalankan server development Flask.

```bash
python run.py
```
Aplikasi akan berjalan secara default di `http://127.0.0.1:5001`.

## Lisensi
Proyek ini dilisensikan di bawah [MIT License](LICENSE).