import secrets
import requests
from decimal import Decimal
from flask import Blueprint, render_template, flash, redirect, url_for, request, current_app
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from datetime import datetime
from flask_login import login_required, current_user
from . import db, bcrypt, mail
from .models import APIKey, Transaction, User, Payment

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def home():
    return render_template('home.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    keys = APIKey.query.filter_by(owner=current_user).all()
    return render_template('dashboard.html', title='Dashboard', keys=keys)

@main_bp.route('/generate-key', methods=['GET', 'POST'])
@login_required
def generate_key():
    KEY_COST = 1000000 # Stored as cents (Rp 10,000.00)
    is_first_key = not APIKey.query.filter_by(owner=current_user).first()

    if not current_user.pin_hash:
        flash('Harap atur PIN keamanan Anda terlebih dahulu.', 'warning')
        return redirect(url_for('main.set_pin', next=request.url))

    if current_user.balance < KEY_COST:
        flash(f'Saldo Anda tidak mencukupi. Biaya pembuatan key adalah Rp {KEY_COST / 100:,.2f}.', 'danger')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        pin = request.form.get('pin')
        store_name = request.form.get('store_name', '').strip()

        if is_first_key and not store_name:
            flash('Untuk API Key pertama, nama toko wajib diisi.', 'danger')
            return redirect(url_for('main.generate_key'))

        if not pin or not bcrypt.check_password_hash(current_user.pin_hash, pin):
            flash('PIN salah. Silakan coba lagi.', 'danger')
            return redirect(url_for('main.generate_key'))

        # Determine store name
        final_store_name = store_name
        if not final_store_name and not is_first_key:
            first_key = APIKey.query.filter_by(owner=current_user).order_by(APIKey.created_at.asc()).first()
            final_store_name = first_key.store_name

        # Generate keys
        public_key = f'pk_test_{secrets.token_hex(16)}'
        secret_key = f'sk_test_{secrets.token_hex(24)}'
        webhook_secret = f'whsec_{secrets.token_hex(24)}'

        # Deduct balance and create records
        current_user.balance -= KEY_COST
        
        new_key = APIKey(
            public_key=public_key,
            secret_key_hash=bcrypt.generate_password_hash(secret_key).decode('utf-8'),
            webhook_secret_hash=bcrypt.generate_password_hash(webhook_secret).decode('utf-8'),
            owner=current_user,
            store_name=final_store_name
        )
        db.session.add(new_key)

        new_transaction = Transaction(user_id=current_user.id, transaction_type='KEY_PURCHASE', amount=KEY_COST, description=f'Pembelian API Key {public_key}')
        db.session.add(new_transaction)
        
        db.session.commit()

        flash('Kunci API berhasil dibuat! Saldo Anda telah dipotong.', 'success')
        return render_template('display_keys.html', public_key=public_key, secret_key=secret_key, webhook_secret=webhook_secret, title='Kunci API Baru')

    return render_template('generate_key_confirm.html', title='Konfirmasi Pembuatan Key', key_cost=KEY_COST, is_first_key=is_first_key)

@main_bp.route('/set-pin', methods=['GET', 'POST'])
@login_required
def set_pin():
    if current_user.pin_hash:
        flash('Anda sudah memiliki PIN.', 'info')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        pin = request.form.get('pin').strip()
        if not pin or not pin.isdigit() or len(pin) != 6:
            flash('PIN harus terdiri dari 6 angka.', 'danger')
            return redirect(url_for('main.set_pin'))
        
        pin_hash = bcrypt.generate_password_hash(pin).decode('utf-8')
        current_user.pin_hash = pin_hash
        db.session.commit()
        flash('PIN keamanan berhasil diatur!', 'success')
        
        next_page = request.form.get('next')
        if next_page and next_page.startswith('/'):
            return redirect(next_page)
        else:
            return redirect(url_for('main.dashboard'))

    return render_template('set_pin.html', title='Atur PIN Keamanan')



@main_bp.route('/history')
@login_required
def history():
    transactions = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.timestamp.desc()).all()
    return render_template('history.html', title='Riwayat Transaksi', transactions=transactions)

@main_bp.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    if not current_user.pin_hash:
        flash('Anda harus mengatur PIN sebelum bisa melakukan transfer.', 'warning')
        return redirect(url_for('main.set_pin', next=request.url))

    if request.method == 'POST':
        recipient_email = request.form.get('recipient_email')
        try:
            amount_decimal = Decimal(request.form.get('amount'))
            amount = int(amount_decimal * 100) # Convert to cents
        except:
            flash('Jumlah tidak valid.', 'danger')
            return redirect(url_for('main.transfer'))
        
        pin = request.form.get('pin').strip()

        if not recipient_email or amount <= 0 or not pin:
            flash('Semua field harus diisi.', 'danger')
            return redirect(url_for('main.transfer'))

        if recipient_email == current_user.email:
            flash('Anda tidak bisa mengirim uang ke diri sendiri.', 'danger')
            return redirect(url_for('main.transfer'))

        if not bcrypt.check_password_hash(current_user.pin_hash, pin):
            flash('PIN salah.', 'danger')
            return redirect(url_for('main.transfer'))

        if current_user.balance < amount:
            flash('Saldo tidak mencukupi.', 'danger')
            return redirect(url_for('main.transfer'))

        recipient = User.query.filter_by(email=recipient_email).first()
        if not recipient:
            flash('Pengguna penerima tidak ditemukan.', 'danger')
            return redirect(url_for('main.transfer'))

        try:
            current_user.balance -= amount
            recipient.balance += amount

            sender_tx = Transaction(
                user_id=current_user.id,
                transaction_type='TRANSFER_OUT',
                amount=amount,
                description=f'Transfer ke {recipient.email}',
                counterparty_id=recipient.id
            )
            db.session.add(sender_tx)

            recipient_tx = Transaction(
                user_id=recipient.id,
                transaction_type='TRANSFER_IN',
                amount=amount,
                description=f'Transfer dari {current_user.email}',
                counterparty_id=current_user.id
            )
            db.session.add(recipient_tx)

            db.session.commit()
            flash(f'Berhasil mentransfer Rp {amount / 100:,.2f} ke {recipient.email}.', 'success')
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            db.session.rollback()
            flash('Terjadi kesalahan saat transfer. Coba lagi.', 'danger')
            return redirect(url_for('main.transfer'))

    return render_template('transfer.html', title='Transfer Saldo')

@main_bp.route('/pay/<signed_payment_id>', methods=['GET', 'POST'])
@login_required
def pay_page(signed_payment_id):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        payment_id = serializer.loads(signed_payment_id, salt='payment-url-salt', max_age=600) # 10 minute expiry
    except (SignatureExpired, BadTimeSignature):
        flash('Link pembayaran tidak valid atau sudah kedaluwarsa.', 'danger')
        return redirect(url_for('main.home'))

    payment = Payment.query.filter_by(payment_id=payment_id).first()

    if not payment:
        flash('Sesi pembayaran ini tidak ditemukan.', 'danger')
        return redirect(url_for('main.home'))

    if payment.status != 'PENDING':
        flash('Sesi pembayaran ini sudah selesai atau kedaluwarsa.', 'info')
        return redirect(url_for('main.dashboard'))

    if current_user.id == payment.merchant_id:
        flash('Anda tidak bisa membayar ke diri Anda sendiri.', 'warning')
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        pin = request.form.get('pin').strip()
        # Split PIN checks for better error messages
        if not current_user.pin_hash:
            flash('Anda belum mengatur PIN keamanan. Silakan atur di dashboard.', 'warning')
            return redirect(url_for('main.set_pin', next=request.url))
        
        if not bcrypt.check_password_hash(current_user.pin_hash, pin):
            flash('PIN yang Anda masukkan salah.', 'danger')
            return render_template('pay_page.html', title='Konfirmasi Pembayaran', payment=payment)

        if current_user.balance < payment.amount:
            flash('Saldo Anda tidak mencukupi untuk melakukan pembayaran ini.', 'danger')
            return render_template('pay_page.html', title='Konfirmasi Pembayaran', payment=payment)

        # Execute Transaction
        payer = current_user
        merchant = payment.merchant

        payer.balance -= payment.amount
        merchant.balance += payment.amount

        payment.status = 'PAID'
        payment.payer_id = payer.id
        payment.paid_at = datetime.utcnow()

        # Find the API key used for this payment to get the correct store name
        # This requires a link between Payment and APIKey, which we don't have.
        # SIMPLIFICATION: We'll find the API key via the merchant. This is not perfect if a merchant has multiple keys.
        # A better approach would be to store public_key on the Payment object.
        api_key = APIKey.query.filter_by(user_id=merchant.id).first() # Simplified logic
        store_name = api_key.store_name if api_key else merchant.email

        # Create transaction records
        payer_tx = Transaction(user_id=payer.id, transaction_type='PAYMENT_OUT', amount=payment.amount, description=f'Pembayaran ke {store_name} (Order: {payment.merchant_order_id})', counterparty_id=merchant.id)
        merchant_tx = Transaction(user_id=merchant.id, transaction_type='PAYMENT_IN', amount=payment.amount, description=f'Pembayaran dari {payer.email} (Order: {payment.merchant_order_id})', counterparty_id=payer.id)
        
        db.session.add(payer_tx)
        db.session.add(merchant_tx)
        db.session.commit()

        # First, find which API key was used for this payment.
        # This is a simplification. In a real app, you might store this on the payment object.
        # For now, we'll just find the first key of the merchant.
        api_key = APIKey.query.filter_by(user_id=merchant.id).first()
        webhook_url = api_key.webhook_url if api_key else None

        if webhook_url:
            try:
                webhook_payload = {
                    'payment_id': payment.payment_id,
                    'merchant_order_id': payment.merchant_order_id,
                    'status': payment.status,
                    'amount': payment.amount,
                    'paid_at': payment.paid_at.isoformat()
                }
                requests.post(webhook_url, json=webhook_payload, timeout=5)
                print(f"INFO: Webhook sent to {webhook_url} for payment {payment.payment_id}")
            except requests.exceptions.RequestException as e:
                print(f"ERROR: Failed to send webhook for payment {payment.payment_id}. Error: {e}")
        else:
            print(f"INFO: Merchant {payment.merchant.email} has no webhook URL set. Skipping webhook.")

        flash('Pembayaran berhasil!', 'success')
        if payment.redirect_url_success:
            return redirect(payment.redirect_url_success)
        else:
            return redirect(url_for('main.dashboard'))

    return render_template('pay_page.html', title='Konfirmasi Pembayaran', payment=payment)

@main_bp.route('/delete-key', methods=['POST'])
@login_required
def delete_key():
    key_id = request.form.get('key_id')
    key_to_delete = APIKey.query.get(key_id)

    if key_to_delete and key_to_delete.user_id == current_user.id:
        db.session.delete(key_to_delete)
        db.session.commit()
        flash('API Key berhasil dihapus.', 'success')
    else:
        flash('Gagal menghapus key. Key tidak ditemukan atau bukan milik Anda.', 'danger')
    
    return redirect(url_for('main.dashboard'))

@main_bp.route('/reset-key', methods=['POST'])
@login_required
def reset_key():
    key_id = request.form.get('key_id')
    key_to_reset = APIKey.query.get(key_id)

    if not key_to_reset or key_to_reset.user_id != current_user.id:
        flash('Gagal mereset key. Key tidak ditemukan atau bukan milik Anda.', 'danger')
        return redirect(url_for('main.dashboard'))

    # Generate new secrets
    new_secret_key = f'sk_test_{secrets.token_hex(24)}'
    new_webhook_secret = f'whsec_{secrets.token_hex(24)}'

    # Hash and update
    key_to_reset.secret_key_hash = bcrypt.generate_password_hash(new_secret_key).decode('utf-8')
    key_to_reset.webhook_secret_hash = bcrypt.generate_password_hash(new_webhook_secret).decode('utf-8')
    db.session.commit()

    flash('API Key berhasil direset! Harap simpan Secret Key dan Webhook Secret baru Anda.', 'success')
    return render_template('display_keys.html',
                           public_key=key_to_reset.public_key, # Public key stays the same
                           secret_key=new_secret_key,
                           webhook_secret=new_webhook_secret,
                           title='Kunci API Telah Direset')


# --- Static & Info Pages ---

@main_bp.route('/terms')
def terms():
    title = 'Terms of Service'
    subtitle = 'Aturan dan Kondisi Penggunaan Layanan GabutPay.'
    content = '''
        <h4>1. Penerimaan Aturan</h4>
        <p>Dengan menggunakan layanan GabutPay (selanjutnya disebut "Layanan"), Anda setuju untuk terikat oleh Syarat dan Ketentuan ini. Layanan ini adalah platform simulasi dan tidak boleh digunakan untuk transaksi keuangan nyata.</p>
        <h4>2. Deskripsi Layanan</h4>
        <p>GabutPay adalah platform e-wallet simulasi yang dirancang untuk tujuan pengujian dan pengembangan. Semua transaksi, saldo, dan data bersifat fiktif.</p>
        <h4>3. Penghentian Akun</h4>
        <p>Kami berhak untuk menangguhkan atau menghentikan akun Anda kapan saja tanpa pemberitahuan jika terjadi penyalahgunaan platform.</p>
    '''
    return render_template('static_page.html', title=title, subtitle=subtitle, content=content)

@main_bp.route('/privacy')
def privacy():
    title = 'Privacy Policy'
    subtitle = 'Bagaimana kami mengumpulkan, menggunakan, dan melindungi data Anda.'
    content = '''
        <h4>1. Data yang Kami Kumpulkan</h4>
        <p>Kami menyimpan informasi yang Anda berikan saat pendaftaran, seperti alamat email dan hash dari password/PIN Anda. Kami juga mencatat alamat IP saat pendaftaran untuk mencegah penyalahgunaan bonus dan menyimpan riwayat transaksi fiktif Anda.</p>
        <h4>2. Penggunaan Data</h4>
        <p>Data Anda hanya digunakan untuk fungsionalitas inti dari platform simulasi ini. Kami tidak membagikan data Anda dengan pihak ketiga mana pun. Karena ini adalah platform simulasi, jangan gunakan data pribadi yang sensitif.</p>
    '''
    return render_template('static_page.html', title=title, subtitle=subtitle, content=content)

@main_bp.route('/disclaimer')
def disclaimer():
    title = 'Disclaimer'
    subtitle = 'Pernyataan sanggahan penting.'
    content = '''
        <p>Layanan GabutPay disediakan "sebagaimana adanya" tanpa jaminan apa pun. Ini adalah proyek simulasi dan tidak dimaksudkan untuk penggunaan komersial atau transaksi nyata. Pengembang tidak bertanggung jawab atas kehilangan data atau kerusakan apa pun yang mungkin timbul dari penggunaan layanan ini.</p>
    '''
    return render_template('static_page.html', title=title, subtitle=subtitle, content=content)

@main_bp.route('/security')
def security():
    title = 'Security Statement'
    subtitle = 'Bagaimana kami mengamankan platform simulasi kami.'
    content = '''
        <p>Kami menerapkan beberapa praktik keamanan standar, termasuk:</p>
        <ul>
            <li><strong>Hashing:</strong> Password dan PIN Anda disimpan sebagai hash menggunakan bcrypt, bukan sebagai teks biasa.</li>
            <li><strong>Verifikasi Email:</strong> Pendaftaran akun baru memerlukan verifikasi melalui One-Time Password (OTP) yang dikirim ke email Anda.</li>
            <li><strong>Otentikasi API:</strong> Akses API antar server diotentikasi menggunakan Public Key.</li>
            <li><strong>URL Aman:</strong> Link untuk reset password/PIN dan pembayaran dibuat unik dan memiliki batas waktu.</li>
        </ul>
    '''
    return render_template('static_page.html', title=title, subtitle=subtitle, content=content)

@main_bp.route('/docs')

def docs():

    title = 'Panduan Anti-Bingung GabutPay'

    subtitle = 'Ikuti langkah ini. Copy-paste kodenya. Dijamin berhasil.'

    content = '''

        <div class="alert alert-primary">Panduan ini mengasumsikan Anda sudah punya akun GabutPay. Jika belum, silakan daftar dulu.</div>



        <h3 class="mt-5">Bagian 1: Yang Anda Lakukan di Website GabutPay</h3>

        <p>Ini adalah persiapan awal. Anda hanya perlu melakukannya sekali.</p>

        <ul class="list-group">

            <li class="list-group-item">✅ <b>Langkah 1: Atur Nama Toko & Webhook</b><br>Buka halaman <code>Pengaturan</code>. Isi <b>Nama Toko</b> dan <b>URL Webhook</b> Anda. URL Webhook adalah alamat di server Anda yang akan menerima notifikasi pembayaran (contoh: <code>https://toko-anda.com/webhook</code>).</li>

            <li class="list-group-item">✅ <b>Langkah 2: Buat API Key</b><br>Buka <code>Dashboard</code>, klik <b>Generate New API Key</b>. Isi nama toko (wajib untuk key pertama), lalu selesaikan prosesnya.</li>

            <li class="list-group-item">✅ <b>Langkah 3: Salin Public Key</b><br>Setelah key dibuat, Anda akan melihat daftar API Key. <strong>Salin (copy) Public Key</strong> Anda. Ini akan kita gunakan di kode Anda.</li>

        </ul>



        <h3 class="mt-5">Bagian 2: Yang Anda Lakukan di Kode Anda</h3>

        <p>Sekarang kita akan menulis kode di server website Anda.</p>



        <h5 class="mt-4">Langkah 4: Kode untuk Memulai Pembayaran</h5>

        <p>Saat pelanggan Anda klik tombol "Beli", jalankan kode di bawah ini di server Anda. Tugas kode ini adalah meminta link pembayaran ke GabutPay.</p>

        <pre class="bg-light p-3 rounded"><code>

# --- CONTOH KODE DI SERVER ANDA (PYTHON) ---



import requests



# Ganti dengan Public Key yang sudah Anda salin dari Langkah 3

PUBLIC_KEY_ANDA = "GANTI_DENGAN_PUBLIC_KEY_ANDA"



# Ganti dengan Alamat IP & Port server GabutPay Anda

# PENTING: Jangan gunakan localhost jika ingin diakses dari perangkat lain!

URL_API_GABUTPAY = "http://192.168.100.9:5001/api/v1/create-payment"



# Detail pesanan dari website Anda

pesanan = {

    "amount": 1000000,  # Harga dalam SEN (Rp 10.000 = 1000000)

    "merchant_order_id": "INV-XYZ-789",

    "description": "Pembelian item premium",

    "redirect_url_success": "https://website-anda.com/pembayaran/sukses"

}



# Kirim permintaan ke GabutPay

response = requests.post(

    URL_API_GABUTPAY,

    json=pesanan,

    headers={'X-PUBLIC-KEY': PUBLIC_KEY_ANDA}

)



# Cek apakah permintaan berhasil

if response.status_code == 201:

    # Ambil link pembayaran dari balasan GabutPay

    link_pembayaran = response.json().get('payment_url')

    

    # Arahkan pelanggan Anda ke link tersebut

    # Contoh di Flask: return redirect(link_pembayaran)

    print(f"BERHASIL! Arahkan pelanggan ke: {link_pembayaran}")

else:

    print(f"GAGAL! Error dari GabutPay: {response.text}")



        </code></pre>



        <div class="alert alert-danger mt-3">

            <h6>Perhatian! Dua Hal Paling Sering Bikin Error:</h6>

            <ol>

                <li><b>Salah Mengisi `amount`</b>: Nilai <strong>HARUS</strong> dalam format Angka (Integer) dan dalam satuan <strong>SEN</strong>. Untuk Rp 50.000, Anda harus menulis <code>5000000</code>.</li>

                <li><b>Salah Mengisi `URL_API_GABUTPAY`</b>: Jika Anda ingin tes dari HP atau komputer lain, <strong>JANGAN</strong> gunakan <code>localhost</code>. Gunakan alamat IP lokal dari komputer yang menjalankan GabutPay (contoh: <code>http://192.168.1.10:5001</code>).</li>

            </ol>

        </div>



        <h5 class="mt-4">Langkah 5: Kode untuk Menerima Notifikasi (Webhook)</h5>

        <p>Ini adalah "penerima telepon" di server Anda. Buat sebuah URL (endpoint) yang cocok dengan yang Anda masukkan di Langkah 1.</p>

        <pre class="bg-light p-3 rounded"><code>

# --- CONTOH KODE WEBHOOK DI SERVER ANDA (FLASK) ---



@app.route("/webhook", methods=['POST'])

def terima_notifikasi_gabutpay():

    data_pembayaran = request.get_json()



    if data_pembayaran.get("status") == "PAID":

        id_pesanan = data_pembayaran.get("merchant_order_id")

        

        # Pesanan LUNAS! Lakukan proses bisnis Anda di sini.

        # Contoh: Update database, kirim email, dll.

        print(f"Pembayaran untuk pesanan {id_pesanan} telah lunas!")



    # Selalu balas dengan status 200 OK

    return jsonify({"status": "diterima"}), 200



        </code></pre>



        <h3 class="mt-5">Alur Data Super Sederhana</h3>

        <p><code>Toko Anda</code> ➡️ Minta Link Pembayaran ke <code>GabutPay</code> ➡️ <code>GabutPay</code> Kasih Link ➡️ <code>Toko Anda</code> Arahkan Pelanggan ke Link ➡️ <code>GabutPay</code> Terima Pembayaran ➡️ <code>GabutPay</code> Kirim Notifikasi ke <code>Webhook Toko Anda</code>.</p>

    '''

    return render_template('static_page.html', title=title, subtitle=subtitle, content=content)

@main_bp.route('/changelog')
def changelog():
    title = 'Changelog'
    subtitle = 'Catatan perubahan dan versi aplikasi.'
    content = '''
        <ul>
            <li><b>v1.2 (Oktober 2025):</b> Penambahan halaman informasional (ToS, Privacy, dll) dan sistem laporan bug.</li>
            <li><b>v1.1 (Oktober 2025):</b> Penambahan fitur Lupa Password & Lupa PIN.</li>
            <li><b>v1.0 (Oktober 2025):</b> Peluncuran awal GabutPay dengan fitur dasar e-wallet, API pembayaran, dan sistem otentikasi.</li>
        </ul>
    '''
    return render_template('static_page.html', title=title, subtitle=subtitle, content=content)

@main_bp.route('/support')
def support():
    title = 'Support / Help Center'
    subtitle = 'Butuh bantuan? Cari di sini.'
    content = '''
        <h4>Pertanyaan Umum (FAQ)</h4>
        <p><strong>Q: Apakah ini layanan pembayaran sungguhan?</strong><br>A: Bukan. Ini adalah platform simulasi hanya untuk tujuan pengembangan dan pengujian.</p>
        <p><strong>Q: Apakah saldo saya bisa diuangkan?</strong><br>A: Tidak. Semua saldo adalah fiktif.</p>
        <p>Jika Anda menemukan bug atau punya masukan, silakan gunakan halaman <a href="/bug-report">Lapor Bug</a>.</p>
    '''
    return render_template('static_page.html', title=title, subtitle=subtitle, content=content)

@main_bp.route('/credits')
def credits():
    title = 'Attribution / Credits'
    subtitle = 'Aplikasi ini adalah hasil kolaborasi antara manusia dan kecerdasan buatan.'
    content = '''
        <h4>Catatan Mengenai Pembuatan Aplikasi Ini</h4>
        <p class="lead">Seluruh aplikasi GabutPay yang sedang Anda gunakan ini—mulai dari logika backend di Python, struktur database, desain frontend, hingga alur API yang kompleks—dirancang, ditulis, dan diperbaiki sepenuhnya oleh sebuah Large Language Model (AI) dari Google.</p>
        <p>Proyek ini adalah sebuah demonstrasi nyata bagaimana AI dapat berfungsi sebagai partner kolaboratif dalam dunia pengembangan perangkat lunak, membantu menerjemahkan ide menjadi kode fungsional selangkah demi selangkah.</p>
        <hr>
        <h5>Teknologi yang Digunakan</h5>
        <p>Dalam prosesnya, AI memilih dan menggunakan berbagai teknologi open source yang luar biasa, termasuk:</p>
        <ul>
            <li>Flask</li>
            <li>Flask-SQLAlchemy</li>
            <li>Flask-Login</li>
            <li>Flask-Bcrypt</li>
            <li>Flask-Mail</li>
            <li>Bootstrap</li>
        </ul>
    '''
    return render_template('static_page.html', title=title, subtitle=subtitle, content=content)

@main_bp.route('/bug-report', methods=['GET', 'POST'])
def bug_report():
    if request.method == 'POST':
        subject = request.form.get('subject')
        description = request.form.get('description')
        
        user_info = "Pengguna: Anonim"
        if current_user.is_authenticated:
            user_info = f"Pengguna: {current_user.email} (ID: {current_user.id})"

        msg = Message(f"Laporan Bug/Feedback: {subject}",
                      sender=current_app.config['MAIL_USERNAME'],
                      recipients=[current_app.config['ADMIN_EMAIL']]) # Menggunakan email admin
        
        msg.body = f"""Laporan baru diterima.\n\nDari: {user_info}\n\nDeskripsi:\n{description}"""
        
        try:
            mail.send(msg)
            flash('Terima kasih! Laporan Anda telah berhasil dikirim.', 'success')
        except Exception as e:
            print(f"ERROR sending bug report email: {e}")
            flash('Gagal mengirim laporan. Silakan coba lagi nanti.', 'danger')

        return redirect(url_for('main.home'))
    return render_template('admin_edit_user.html', title=f'Edit Pengguna: {user.email}', user=user)

@main_bp.route('/edit-key/<int:key_id>', methods=['GET', 'POST'])
@login_required
def edit_key(key_id):
    api_key = APIKey.query.get_or_404(key_id)
    if api_key.user_id != current_user.id:
        abort(403)

    if request.method == 'POST':
        webhook_url = request.form.get('webhook_url')
        if webhook_url and not (webhook_url.startswith('http://') or webhook_url.startswith('https://')):
            flash('URL Webhook tidak valid.', 'danger')
        else:
            api_key.webhook_url = webhook_url
            db.session.commit()
            flash('URL Webhook berhasil diperbarui!', 'success')
        return redirect(url_for('main.dashboard'))

    return render_template('edit_key.html', title='Edit API Key', api_key=api_key)


