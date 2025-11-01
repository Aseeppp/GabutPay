import secrets
from datetime import datetime, timedelta
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from flask_mail import Message
from . import db, bcrypt, mail
from .models import User, Transaction

auth_bp = Blueprint('auth', __name__)

def send_otp_email(user, otp):
    msg = Message('Kode Verifikasi GabutPay Anda',
                  sender=current_app.config['MAIL_USERNAME'],
                  recipients=[user.email])
    msg.body = f'''Selamat datang di GabutPay!

Gunakan kode ini untuk memverifikasi akun Anda:

{otp}

Kode ini akan kedaluwarsa dalam 10 menit.

Jika Anda tidak merasa mendaftar, abaikan email ini.
'''
    try:
        mail.send(msg)
    except Exception as e:
        # For development, print the error if mail fails to send
        print(f"Error sending email: {e}")
        flash('Gagal mengirim email verifikasi. Silakan hubungi support.', 'danger')

@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        if user and user.is_verified:
            flash('Email sudah terdaftar dan terverifikasi. Silakan login.', 'warning')
            return redirect(url_for('auth.login'))

        otp = secrets.token_hex(3).upper()
        otp_hash = bcrypt.generate_password_hash(otp).decode('utf-8')
        otp_expiry = datetime.utcnow() + timedelta(minutes=10)

        if user and not user.is_verified: # User exists but not verified, update OTP
            user.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
            user.otp_hash = otp_hash
            user.otp_expiry = otp_expiry
            user.registration_ip = request.remote_addr
        else: # New user
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            new_user = User(email=email, password_hash=hashed_password, otp_hash=otp_hash, otp_expiry=otp_expiry, registration_ip=request.remote_addr)
            db.session.add(new_user)
        
        db.session.commit()
        send_otp_email(user if user else new_user, otp)
        
        flash('Pendaftaran berhasil! Kode OTP telah dikirim ke email Anda.', 'info')
        return redirect(url_for('auth.verify_otp', email=email))

    return render_template('register.html', title='Register')

@auth_bp.route('/verify-otp/<email>', methods=['GET', 'POST'])
def verify_otp(email):
    user = User.query.filter_by(email=email).first_or_404()
    if user.is_verified:
        flash('Akun sudah terverifikasi. Silakan login.', 'info')
        return redirect(url_for('auth.login'))

    if request.method == 'POST':
        otp_form = request.form.get('otp')
        if not user.otp_hash or not user.otp_expiry or datetime.utcnow() > user.otp_expiry:
            flash('OTP sudah kedaluwarsa. Silakan daftar ulang untuk mendapatkan OTP baru.', 'danger')
            return redirect(url_for('auth.register'))

        if bcrypt.check_password_hash(user.otp_hash, otp_form):
            user.is_verified = True
            user.otp_hash = None
            user.otp_expiry = None

            # Check for existing IP and grant bonus
            existing_user_with_ip = User.query.filter(User.id != user.id, User.registration_ip == user.registration_ip, User.is_verified == True).first()
            if not existing_user_with_ip:
                user.balance = 5000000 # 50k bonus
                bonus_tx = Transaction(user_id=user.id, transaction_type='WELCOME_BONUS', amount=5000000, description='Bonus selamat datang')
                db.session.add(bonus_tx)
                flash('Verifikasi berhasil! Anda mendapatkan bonus saldo Rp 50.000,00.', 'success')
            else:
                flash('Verifikasi berhasil! Silakan login.', 'success')

            db.session.commit()
            return redirect(url_for('auth.login'))
        else:
            flash('OTP salah. Silakan coba lagi.', 'danger')

    return render_template('verify_otp.html', title='Verifikasi OTP', email=email)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if user and bcrypt.check_password_hash(user.password_hash, password):
            if user.banned_until and user.banned_until > datetime.utcnow():
                flash(f'Akun Anda sedang diblokir. Coba lagi setelah {user.banned_until.strftime("%d %b %Y %H:%M:%S")} UTC.', 'danger')
                return redirect(url_for('auth.login'))

            if not user.is_verified:
                flash('Akun Anda belum diverifikasi. Silakan cek email Anda untuk kode OTP.', 'warning')
                return redirect(url_for('auth.verify_otp', email=user.email))
            
            login_user(user, remember=True)
            next_page = request.form.get('next')
            # Security check to prevent open redirect attacks
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('main.dashboard')
            flash('Login berhasil!', 'success')
            return redirect(next_page)
        else:
            flash('Login gagal. Periksa kembali email dan password Anda.', 'danger')

    return render_template('login.html', title='Login')

@auth_bp.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('main.home'))

def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Permintaan Reset Password GabutPay',
                  sender=current_app.config['MAIL_USERNAME'],
                  recipients=[user.email])
    msg.body = f'''Untuk mereset password Anda, kunjungi link berikut:
{url_for('auth.reset_token', token=token, _external=True)}

Link ini akan kedaluwarsa dalam 30 menit.

Jika Anda tidak merasa meminta ini, abaikan saja email ini.
'''
    try:
        mail.send(msg)
    except Exception as e:
        print(f"Error sending email: {e}")

@auth_bp.route("/reset-password", methods=['GET', 'POST'])
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user:
            send_reset_email(user)
        flash('Jika akun dengan email tersebut ada, instruksi reset password telah dikirim.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('reset_request.html', title='Reset Password')


@auth_bp.route("/reset-password/<token>", methods=['GET', 'POST'])
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('Token tidak valid atau sudah kedaluwarsa.', 'warning')
        return redirect(url_for('auth.reset_request'))
    if request.method == 'POST':
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if password != confirm_password:
            flash('Konfirmasi password tidak cocok.', 'danger')
            return render_template('reset_token.html', title='Reset Password', token=token)

        user.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
        db.session.commit()
        flash('Password Anda telah berhasil diupdate! Silakan login.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('reset_token.html', title='Reset Password', token=token)

def send_pin_reset_email(user):
    token = user.get_pin_reset_token()
    msg = Message('Permintaan Reset PIN GabutPay',
                  sender=current_app.config['MAIL_USERNAME'],
                  recipients=[user.email])
    msg.body = f'''Untuk mereset PIN Anda, kunjungi link berikut:
{url_for('auth.reset_pin_token', token=token, _external=True)}

Link ini akan kedaluwarsa dalam 30 menit.

Jika Anda tidak merasa meminta ini, abaikan saja email ini.
'''
    try:
        mail.send(msg)
    except Exception as e:
        print(f"Error sending email: {e}")

@auth_bp.route("/reset-pin", methods=['GET', 'POST'])
@login_required
def reset_pin_request():
    if request.method == 'POST':
        send_pin_reset_email(current_user)
        flash('Link untuk mereset PIN telah dikirim ke email Anda.', 'info')
        return redirect(url_for('main.dashboard'))
    return render_template('reset_pin_request.html', title='Reset PIN')


@auth_bp.route("/reset-pin/<token>", methods=['GET', 'POST'])
@login_required
def reset_pin_token(token):
    user = User.verify_pin_reset_token(token)
    if user is None or user.id != current_user.id:
        flash('Token tidak valid atau sudah kedaluwarsa.', 'warning')
        return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        pin = request.form['pin'].strip()
        confirm_pin = request.form['confirm_pin'].strip()

        if not pin or not pin.isdigit() or len(pin) != 6:
            flash('PIN harus terdiri dari 6 angka.', 'danger')
            return render_template('reset_pin_token.html', title='Reset PIN Baru', token=token)

        if pin != confirm_pin:
            flash('Konfirmasi PIN tidak cocok.', 'danger')
            return render_template('reset_pin_token.html', title='Reset PIN Baru', token=token)

        user.pin_hash = bcrypt.generate_password_hash(pin).decode('utf-8')
        db.session.commit()
        flash('PIN Anda telah berhasil diupdate!', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('reset_pin_token.html', title='Reset PIN Baru', token=token)