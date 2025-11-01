# GabutPay: Simulasi E-Wallet & Payment Gateway

GabutPay adalah sebuah proyek simulasi yang berfungsi ganda: sebagai **dompet digital (e-wallet)** untuk pengguna akhir dan sebagai **payment gateway** untuk para developer. Aplikasi ini dirancang sebagai sebuah studi kasus dan portfolio untuk mendemonstrasikan pembuatan aplikasi web finansial yang cukup kompleks dengan Python dan Flask.

Secara unik, seluruh aplikasi ini—mulai dari logika backend, struktur database, hingga alur API—dirancang dan ditulis oleh sebuah Large Language Model (AI) dari Google sebagai bukti nyata kolaborasi antara manusia dan AI dalam pengembangan perangkat lunak.

## Konsep Utama

*   **Fungsi Ganda:** Pengguna bisa mendaftar, memiliki saldo, dan mentransfer uang seperti e-wallet pada umumnya. Di sisi lain, mereka juga bisa bertindak sebagai *merchant* dengan membuat API key untuk menerima pembayaran di aplikasi atau website mereka.
*   **Keamanan (Simulasi):** Meskipun ini hanya simulasi, beberapa praktik keamanan standar diterapkan, seperti *hashing* password & PIN (menggunakan bcrypt), verifikasi pendaftaran via OTP email, dan penggunaan PIN untuk setiap transaksi sensitif.
*   **Bonus Pendaftaran Unik:** Untuk mencegah penyalahgunaan dan sebagai strategi akuisisi, pengguna baru akan mendapatkan "Bonus Selamat Datang" hanya jika belum ada akun lain yang terverifikasi dari alamat IP yang sama.
*   **API Untuk Merchant:** Developer dapat dengan mudah berintegrasi dengan GabutPay. Cukup dengan membuat API Key (yang dikenakan biaya dari saldo), mereka bisa memanggil satu endpoint sederhana untuk membuat link pembayaran bagi pelanggan mereka.

## Fitur Rinci

#### Untuk Pengguna (Dompet Digital)
- **Registrasi & Verifikasi:** Alur pendaftaran aman dengan verifikasi OTP via email.
- **Manajemen Saldo:** Melihat saldo, riwayat transaksi, dan menerima bonus pendaftaran.
- **Transfer Dana:** Mengirim uang ke sesama pengguna GabutPay dengan aman menggunakan PIN.
- **Keamanan Akun:** Mengatur PIN 6 digit, serta fitur lupa password dan lupa PIN melalui email.

#### Untuk Developer (Payment Gateway)
- **Dasbor Merchant:** Setelah login, pengguna memiliki akses ke dasbor untuk mengelola API Key.
- **Pembuatan API Key:** Pengguna dapat membeli API Key seharga Rp 10.000 (dipotong dari saldo) untuk mulai menerima pembayaran.
- **Integrasi Sederhana:** Cukup memanggil satu endpoint API (`/api/v1/create-payment`) untuk menghasilkan URL pembayaran yang aman dan berbatas waktu.
- **Notifikasi Webhook:** Menerima notifikasi *real-time* ke URL yang telah ditentukan setiap kali pembayaran berhasil.
- **Dokumentasi:** Terdapat halaman `/docs` yang menjelaskan langkah-langkah integrasi API.

## Teknologi yang Digunakan

*   **Backend:** Python, Flask
*   **Database:** Flask-SQLAlchemy (SQLite by default)
*   **Otentikasi:** Flask-Login, Flask-Bcrypt
*   **Email:** Flask-Mail
*   **Frontend:** Bootstrap 5 (via CDN)

## Struktur Proyek

Proyek ini terdiri dari dua bagian utama:

1.  `GabutPay` (Aplikasi Utama): Inti dari aplikasi e-wallet dan payment gateway.
2.  `toko_online`: Sebuah aplikasi Flask minimalis yang berperan sebagai contoh toko online (merchant) yang menggunakan API dari `GabutPay`.

## Cara Menjalankan Proyek

### Menjalankan Secara Lokal

Untuk menjalankan proyek ini di komputer Anda (mode development). Anda perlu menjalankan kedua aplikasi (`GabutPay` dan `toko_online`) di dua terminal yang berbeda.

#### 1. Setup Aplikasi Utama (GabutPay)

```bash
# 1. Clone repositori
git clone https://github.com/Aseeppp/GabutPay.git
cd GabutPay

# 2. Buat dan aktifkan virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependensi
pip install -r requirements.txt

# 4. Buat file .env dan isi konfigurasinya
# Contoh:
# SECRET_KEY=kunci_rahasia_super_aman
# MAIL_SERVER=smtp.gmail.com
# MAIL_PORT=587
# MAIL_USE_TLS=True
# MAIL_USERNAME=email_gmail_anda@gmail.com
# MAIL_PASSWORD=password_aplikasi_gmail_anda
# ADMIN_EMAIL=email_penerima_laporan_bug@example.com

# 5. Inisialisasi database dan buat admin pertama
python create_admin.py

# 6. Jalankan aplikasi GabutPay
python run.py
```
*Aplikasi akan berjalan di `http://127.0.0.1:5001`.* 

#### 2. Setup Aplikasi Contoh (Toko Online)

Buka terminal **kedua**.

```bash
# 1. Masuk ke direktori toko_online
cd GabutPay/toko_online

# 2. Install dependensi
pip install -r requirements.txt

# 3. Jalankan aplikasi toko online
python run_toko.py
```
*Aplikasi akan berjalan di `http://127.0.0.1:5002`.* 

### Menjalankan di Platform Hosting (Contoh: Railway)

Ketika Anda men-deploy aplikasi ini ke platform hosting:
1.  Platform akan secara otomatis mendeteksi `run.py` dan `requirements.txt` untuk menjalankan aplikasi `GabutPay`.
2.  Anda perlu mengkonfigurasi **environment variables** (seperti `SECRET_KEY`, `MAIL_USERNAME`, dll.) melalui dasbor hosting Anda, bukan dari file `.env`.
3.  Platform akan memberikan **URL publik** (misalnya, `https://gabutpay-production-xxxx.up.railway.app`). URL inilah yang akan menjadi alamat utama aplikasi Anda.
4.  Untuk aplikasi `toko_online`, Anda perlu men-deploy-nya sebagai layanan terpisah dan mengubah variabel `GABUTPAY_API_BASE_URL` di dalam `toko_online/run_toko.py` agar menunjuk ke URL publik `GabutPay` Anda.
