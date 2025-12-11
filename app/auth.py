import secrets
from datetime import datetime, timedelta
from threading import Thread
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, current_user, login_required
from flask_mail import Message
from . import db, bcrypt, mail, limiter
from .models import User, Transaction
from .forms import (
    RegistrationForm, LoginForm, OTPForm, ResetRequestForm, ResetTokenForm,
    ResetPINRequestForm, ResetPINTokenForm
)

auth_bp = Blueprint('auth', __name__)

def send_async_email(app, msg):
    with app.app_context():
        try:
            mail.send(msg)
        except Exception as e:
            app.logger.error(f"Failed to send email in background: {e}")

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
    Thread(target=send_async_email, args=(current_app._get_current_object(), msg)).start()

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
    Thread(target=send_async_email, args=(current_app._get_current_object(), msg)).start()

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
    Thread(target=send_async_email, args=(current_app._get_current_object(), msg)).start()

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("10 per hour")
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = RegistrationForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        
        user = User.query.filter_by(email=email).first()
        if user and user.is_verified:
            flash('Email sudah terdaftar dan terverifikasi. Silakan login.', 'warning')
            return redirect(url_for('auth.login'))

        # Generate a secure 6-digit numeric OTP
        otp = "{:06d}".format(secrets.randbelow(1000000))
        otp_hash = bcrypt.generate_password_hash(otp).decode('utf-8')
        otp_expiry = datetime.utcnow() + timedelta(minutes=10)

        if user and not user.is_verified:
            user.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
            user.otp_hash = otp_hash
            user.otp_expiry = otp_expiry
            user.registration_ip = request.remote_addr
        else:
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            new_user = User(email=email, password_hash=hashed_password, otp_hash=otp_hash, otp_expiry=otp_expiry, registration_ip=request.remote_addr)
            db.session.add(new_user)
        
        db.session.commit()
        send_otp_email(user if user else new_user, otp)
        
        flash('Pendaftaran berhasil! Kode OTP telah dikirim ke email Anda.', 'info')
        return redirect(url_for('auth.verify_otp', email=email))

    return render_template('register.html', title='Register', form=form)

@auth_bp.route('/verify-otp/<email>', methods=['GET', 'POST'])
@limiter.limit("20 per 10 minutes")
def verify_otp(email):
    user = User.query.filter_by(email=email).first_or_404()
    if user.is_verified:
        flash('Akun sudah terverifikasi. Silakan login.', 'info')
        return redirect(url_for('auth.login'))

    form = OTPForm()
    if form.validate_on_submit():
        otp_form = form.otp.data
        if not user.otp_hash or not user.otp_expiry or datetime.utcnow() > user.otp_expiry:
            flash('OTP sudah kedaluwarsa. Silakan daftar ulang untuk mendapatkan OTP baru.', 'danger')
            return redirect(url_for('auth.register'))

        if bcrypt.check_password_hash(user.otp_hash, otp_form):
            user.is_verified = True
            user.otp_hash = None
            user.otp_expiry = None

            existing_user_with_ip = User.query.filter(User.id != user.id, User.registration_ip == user.registration_ip, User.is_verified == True).first()
            if not existing_user_with_ip:
                bonus_amount = current_app.config.get('REGISTRATION_BONUS', 0)
                if bonus_amount > 0:
                    user.balance += bonus_amount
                    bonus_tx = Transaction(user_id=user.id, transaction_type='WELCOME_BONUS', amount=bonus_amount, description='Bonus selamat datang')
                    db.session.add(bonus_tx)
                    flash(f'Verifikasi berhasil! Anda mendapatkan bonus saldo Rp {bonus_amount / 100:,.2f}.', 'success')
                else:
                    flash('Verifikasi berhasil! Silakan login.', 'success')
            else:
                flash('Verifikasi berhasil! Silakan login.', 'success')

            db.session.commit()
            return redirect(url_for('auth.login'))
        else:
            flash('OTP salah. Silakan coba lagi.', 'danger')

    return render_template('verify_otp.html', title='Verifikasi OTP', email=email, form=form)

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("15 per 5 minutes")
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))

    form = LoginForm()
    if form.validate_on_submit():
        email = form.email.data
        password = form.password.data
        user = User.query.filter_by(email=email).first()

        if user and bcrypt.check_password_hash(user.password_hash, password):
            if user.banned_until and user.banned_until > datetime.utcnow():
                flash(f'Akun Anda sedang diblokir. Coba lagi setelah {user.banned_until.strftime("%d %b %Y %H:%M:%S")} UTC.', 'danger')
                return redirect(url_for('auth.login'))

            if not user.is_verified:
                flash('Akun Anda belum diverifikasi. Silakan cek email Anda untuk kode OTP.', 'warning')
                return redirect(url_for('auth.verify_otp', email=user.email))
            
            login_user(user, remember=form.remember.data)

            # --- Daily Login & Streak Logic ---
            today = datetime.utcnow().date()
            
            # Check if it's a new day login
            if user.last_seen is None or user.last_seen.date() < today:
                # It is a new day, grant the bonus
                bonus_amount = current_app.config.get('DAILY_LOGIN_BONUS', 0)
                if bonus_amount > 0:
                    user.balance += bonus_amount
                    bonus_tx = Transaction(
                        user_id=user.id,
                        transaction_type='BONUS',
                        amount=bonus_amount,
                        description='Bonus login harian'
                    )
                    db.session.add(bonus_tx)
                    flash(f'Selamat! Anda mendapatkan bonus login harian sebesar Rp {bonus_amount / 100:,.2f}!', 'success')

                # Update login streak
                if user.last_seen and (today - user.last_seen.date()) == timedelta(days=1):
                    user.login_streak += 1
                    if user.login_streak > 1:
                        flash(f'Beruntun! Anda telah login {user.login_streak} hari berturut-turut.', 'info')
                else:
                    # First login or streak broken
                    user.login_streak = 1
            
            # Update last_seen timestamp regardless
            user.last_seen = datetime.utcnow()
            db.session.commit()
            # --- End of Daily Login & Streak Logic ---

            next_page = request.args.get('next')
            if not next_page or not next_page.startswith('/'):
                next_page = url_for('main.dashboard')
            flash('Login berhasil!', 'success')
            return redirect(next_page)
        else:
            flash('Login gagal. Periksa kembali email dan password Anda.', 'danger')

    return render_template('login.html', title='Login', form=form)

@auth_bp.route("/reset-password", methods=['GET', 'POST'])
@limiter.limit("5 per 15 minutes")
def reset_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    form = ResetRequestForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user:
            send_reset_email(user)
        flash('Jika akun dengan email tersebut ada, instruksi reset password telah dikirim.', 'info')
        return redirect(url_for('auth.login'))
    return render_template('reset_request.html', title='Reset Password', form=form)

@auth_bp.route("/reset-password/<token>", methods=['GET', 'POST'])
@limiter.limit("10 per 15 minutes")
def reset_token(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.home'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('Token tidak valid atau sudah kedaluwarsa.', 'warning')
        return redirect(url_for('auth.reset_request'))
    
    form = ResetTokenForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        user.password_hash = hashed_password
        db.session.commit()
        flash('Password Anda telah berhasil diupdate! Silakan login.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('reset_token.html', title='Reset Password', form=form, token=token)

@auth_bp.route("/logout")
def logout():
    logout_user()
    flash('Anda telah berhasil logout.', 'info')
    return redirect(url_for('main.home'))
@auth_bp.route("/reset-pin", methods=['GET', 'POST'])
@login_required
@limiter.limit("5 per 15 minutes")
def reset_pin_request():
    form = ResetPINRequestForm()
    if form.validate_on_submit():
        send_pin_reset_email(current_user)
        flash('Link untuk mereset PIN telah dikirim ke email Anda.', 'info')
        return redirect(url_for('main.dashboard'))
    return render_template('reset_pin_request.html', title='Reset PIN', form=form)

@auth_bp.route("/reset-pin/<token>", methods=['GET', 'POST'])
@login_required
@limiter.limit("10 per 15 minutes")
def reset_pin_token(token):
    user = User.verify_pin_reset_token(token)
    if user is None or user.id != current_user.id:
        flash('Token tidak valid atau sudah kedaluwarsa.', 'warning')
        return redirect(url_for('main.dashboard'))
    
    form = ResetPINTokenForm()
    if form.validate_on_submit():
        pin = form.pin.data
        user.pin_hash = bcrypt.generate_password_hash(pin).decode('utf-8')
        db.session.commit()
        flash('PIN Anda telah berhasil diupdate!', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('reset_pin_token.html', title='Reset PIN Baru', form=form, token=token)