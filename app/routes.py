import secrets
import requests
import hmac
import hashlib
import json
from decimal import Decimal
from flask import Blueprint, render_template, flash, redirect, url_for, request, current_app, send_from_directory
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from datetime import datetime
from flask_login import login_required, current_user
from . import db, bcrypt, mail
from .models import APIKey, Transaction, User, Payment, SplitBill, SplitBillParticipant
from .utils import encrypt_data, decrypt_data, generate_qr_code
from .push import send_push_notification
from .forms import (
    GenerateKeyForm, SetPINForm, TransferForm, PayPageForm, BugReportForm,
    EditKeyForm, DeleteKeyForm, ResetKeyForm, RequestQRForm, SplitBillForm
)

main_bp = Blueprint('main', __name__)

@main_bp.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js')

def _send_webhook(payment, api_key):
    """Helper function to send a webhook notification."""
    if not api_key or not api_key.webhook_url:
        current_app.logger.info(f"Merchant {payment.merchant.email} has no webhook URL set. Skipping webhook.")
        return

    raw_webhook_secret = None
    if api_key.webhook_secret_encrypted:
        try:
            decrypted_secret_bytes = decrypt_data(api_key.webhook_secret_encrypted)
            if decrypted_secret_bytes:
                raw_webhook_secret = decrypted_secret_bytes.decode('utf-8')
        except Exception as e:
            current_app.logger.error(f"Could not decrypt webhook secret for merchant {payment.merchant.email}. Error: {e}")
            return

    if not raw_webhook_secret:
        current_app.logger.warning(f"Webhook secret not found or could not be decrypted for merchant {payment.merchant.email}. Cannot sign webhook.")
        return

    try:
        webhook_payload = {
            'payment_id': payment.payment_id,
            'merchant_order_id': payment.merchant_order_id,
            'status': payment.status,
            'amount': payment.amount,
            'paid_at': payment.paid_at.isoformat() if payment.paid_at else None
        }
        payload_body = json.dumps(webhook_payload, separators=(',', ':')).encode('utf-8')
        signature = hmac.new(raw_webhook_secret.encode('utf-8'), payload_body, hashlib.sha256).hexdigest()
        headers = {'Content-Type': 'application/json', 'X-GABUTPAY-SIGNATURE': signature}
        
        requests.post(api_key.webhook_url, data=payload_body, headers=headers, timeout=5)
        current_app.logger.info(f"Webhook sent to {api_key.webhook_url} for payment {payment.payment_id}")
    except requests.exceptions.RequestException as e:
        current_app.logger.error(f"Failed to send webhook for payment {payment.payment_id}. Error: {e}")

@main_bp.route('/')
def home():
    return render_template('home.html')

@main_bp.route('/dashboard')
@login_required
def dashboard():
    keys = APIKey.query.filter_by(owner=current_user).all()
    delete_form = DeleteKeyForm()
    reset_form = ResetKeyForm()
    return render_template(
        'dashboard.html', 
        title='Dashboard', 
        keys=keys, 
        delete_form=delete_form, 
        reset_form=reset_form,
        vapid_public_key=current_app.config['VAPID_PUBLIC_KEY']
    )

@main_bp.route('/generate-key', methods=['GET', 'POST'])
@login_required
def generate_key():
    key_cost = current_app.config['KEY_COST']
    first_key = APIKey.query.filter_by(owner=current_user).first()
    is_first_key = first_key is None

    if not current_user.pin_hash:
        flash('Harap atur PIN keamanan Anda terlebih dahulu.', 'warning')
        return redirect(url_for('main.set_pin', next=request.url))

    # Quick check before showing the form, the real check is inside the transaction
    if current_user.balance < key_cost:
        flash(f'Saldo Anda tidak mencukupi. Biaya pembuatan key adalah Rp {key_cost / 100:,.2f}.', 'danger')
        return redirect(url_for('main.dashboard'))

    form = GenerateKeyForm()
    if form.validate_on_submit():
        pin = form.pin.data
        store_name = form.store_name.data.strip()

        if not bcrypt.check_password_hash(current_user.pin_hash, pin):
            flash('PIN salah. Silakan coba lagi.', 'danger')
            return redirect(url_for('main.generate_key'))

        if is_first_key and not store_name:
            flash('Untuk API Key pertama, nama toko wajib diisi.', 'danger')
            return redirect(url_for('main.generate_key'))

        try:
            # Lock the user row to prevent race conditions
            user = db.session.query(User).filter_by(id=current_user.id).with_for_update().one()

            if user.balance < key_cost:
                flash(f'Saldo Anda tidak mencukupi. Biaya pembuatan key adalah Rp {key_cost / 100:,.2f}.', 'danger')
                db.session.rollback()  # Release the lock
                return redirect(url_for('main.dashboard'))

            final_store_name = store_name or (first_key.store_name if first_key else '')

            public_key = f'pk_test_{secrets.token_hex(16)}'
            secret_key = f'sk_test_{secrets.token_hex(24)}'
            webhook_secret = f'whsec_{secrets.token_hex(24)}'

            user.balance -= key_cost
            
            new_key = APIKey(
                public_key=public_key,
                secret_key_hash=bcrypt.generate_password_hash(secret_key).decode('utf-8'),
                secret_key_encrypted=encrypt_data(secret_key.encode('utf-8')),
                webhook_secret_hash=bcrypt.generate_password_hash(webhook_secret).decode('utf-8'),
                webhook_secret_encrypted=encrypt_data(webhook_secret.encode('utf-8')),
                owner=user,
                store_name=final_store_name
            )
            db.session.add(new_key)

            new_transaction = Transaction(user_id=user.id, transaction_type='KEY_PURCHASE', amount=-key_cost, description=f'Pembelian API Key {public_key}')
            db.session.add(new_transaction)
            
            db.session.commit()

            flash('Kunci API berhasil dibuat! Saldo Anda telah dipotong.', 'success')
            return render_template('display_keys.html', public_key=public_key, secret_key=secret_key, webhook_secret=webhook_secret, title='Kunci API Baru')

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error during key generation for user {current_user.id}: {e}")
            flash('Terjadi kesalahan internal saat membuat key. Dana Anda aman.', 'danger')
            return redirect(url_for('main.dashboard'))

    return render_template('generate_key_confirm.html', title='Konfirmasi Pembuatan Key', form=form, key_cost=key_cost, is_first_key=is_first_key)

@main_bp.route('/set-pin', methods=['GET', 'POST'])
@login_required
def set_pin():
    if current_user.pin_hash:
        flash('Anda sudah memiliki PIN.', 'info')
        return redirect(url_for('main.dashboard'))

    form = SetPINForm()
    if form.validate_on_submit():
        pin_hash = bcrypt.generate_password_hash(form.pin.data).decode('utf-8')
        current_user.pin_hash = pin_hash
        db.session.commit()
        flash('PIN keamanan berhasil diatur!', 'success')
        
        next_page = form.next.data
        if next_page and next_page.startswith('/'):
            return redirect(next_page)
        return redirect(url_for('main.dashboard'))
    
    form.next.data = request.args.get('next')
    return render_template('set_pin.html', title='Atur PIN Keamanan', form=form)

@main_bp.route('/history')
@login_required
def history():
    page = request.args.get('page', 1, type=int)
    transactions = Transaction.query.filter_by(user_id=current_user.id).order_by(Transaction.timestamp.desc()).paginate(page=page, per_page=15)
    return render_template('history.html', title='Riwayat Transaksi', transactions=transactions)

@main_bp.route('/transfer', methods=['GET', 'POST'])
@login_required
def transfer():
    if not current_user.pin_hash:
        flash('Anda harus mengatur PIN sebelum bisa melakukan transfer.', 'warning')
        return redirect(url_for('main.set_pin', next=request.url))

    form = TransferForm()
    if form.validate_on_submit():
        recipient_email = form.recipient_email.data
        amount = int(form.amount.data * 100)
        pin = form.pin.data

        if recipient_email == current_user.email:
            flash('Anda tidak bisa mengirim uang ke diri sendiri.', 'danger')
            return redirect(url_for('main.transfer'))

        if not bcrypt.check_password_hash(current_user.pin_hash, pin):
            flash('PIN salah.', 'danger')
            return redirect(url_for('main.transfer'))

        try:
            # Lock rows for update
            sender = db.session.query(User).filter_by(id=current_user.id).with_for_update().one()
            recipient = db.session.query(User).filter(User.email == recipient_email, User.id != sender.id).with_for_update().one_or_none()
            
            if not recipient:
                flash('Pengguna penerima tidak ditemukan.', 'danger')
                db.session.rollback()
                return redirect(url_for('main.transfer'))

            # --- New Fee Logic ---
            base_amount = int(form.amount.data * 100)
            
            # 1. Calculate Payer (Sender) Fee
            payer_fee = int(base_amount * current_app.config['PAYER_FEE_TRANSFER_PERCENT'])
            total_debited = base_amount + payer_fee

            if sender.balance < total_debited:
                flash('Saldo tidak mencukupi untuk melakukan transfer dan membayar biaya layanan.', 'danger')
                db.session.rollback()
                return redirect(url_for('main.transfer'))

            # 2. Calculate Payee (Recipient) Fee
            merchant_fee = int(base_amount * current_app.config['MERCHANT_FEE_PERCENT'])
            recipient_amount = base_amount - merchant_fee
            
            # 3. Update balances
            admin_user = db.session.query(User).filter_by(email='sistem@gabutpay.com').with_for_update().one()
            sender.balance -= total_debited
            recipient.balance += recipient_amount
            admin_user.balance += payer_fee + merchant_fee

            # 4. Create unified Payment record
            transfer_payment = Payment(
                merchant_id=recipient.id,
                payer_id=sender.id,
                amount=base_amount,
                payer_fee=payer_fee,
                merchant_fee=merchant_fee,
                payment_method='TRANSFER',
                merchant_order_id=f'transfer_{secrets.token_hex(8)}',
                description=f'Transfer dari {sender.email} ke {recipient.email}',
                status='PAID',
                paid_at=datetime.utcnow()
            )
            db.session.add(transfer_payment)
            
            # 5. Create transaction records and link them to the Payment
            # Payer side
            sender_tx_1 = Transaction(user_id=sender.id, payment=transfer_payment, transaction_type='TRANSFER_OUT', amount=-base_amount, description=f'Transfer ke {recipient.email}', counterparty_id=recipient.id)
            sender_tx_2 = Transaction(user_id=sender.id, payment=transfer_payment, transaction_type='PAYER_FEE', amount=-payer_fee, description=f'Biaya layanan transfer ke {recipient.email}', counterparty_id=admin_user.id)
            # Recipient side
            recipient_tx = Transaction(user_id=recipient.id, payment=transfer_payment, transaction_type='TRANSFER_IN', amount=recipient_amount, description=f'Transfer dari {sender.email}', counterparty_id=sender.id)
            # Admin side
            admin_tx_1 = Transaction(user_id=admin_user.id, payment=transfer_payment, transaction_type='ADMIN_FEE', amount=merchant_fee, description=f'Biaya admin dari transfer (sisi penerima: {recipient.email})')
            admin_tx_2 = Transaction(user_id=admin_user.id, payment=transfer_payment, transaction_type='ADMIN_FEE', amount=payer_fee, description=f'Biaya layanan dari transfer (sisi pengirim: {sender.email})')

            db.session.add_all([sender_tx_1, sender_tx_2, recipient_tx, admin_tx_1, admin_tx_2])
            db.session.commit()

            # Send push notifications
            try:
                # To recipient
                recipient_payload = { "title": "Transfer Diterima!", "body": f"Anda telah menerima sebesar Rp {Decimal(recipient_amount) / 100:,.2f} dari {sender.email}." }
                send_push_notification(recipient.id, recipient_payload)
                # To sender
                sender_payload = { "title": "Transfer Berhasil", "body": f"Anda berhasil mentransfer Rp {Decimal(base_amount) / 100:,.2f} ke {recipient.email} (Total terpotong: Rp {Decimal(total_debited) / 100:,.2f})." }
                send_push_notification(sender.id, sender_payload)
            except Exception as e:
                current_app.logger.error(f"Failed to send push notification(s) for transfer: {e}")

            flash(f'Berhasil mentransfer Rp {Decimal(base_amount) / 100:,.2f} ke {recipient.email}.', 'success')
            return redirect(url_for('main.payment_details', payment_id=transfer_payment.payment_id))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error during transfer: {e}")
            flash('Terjadi kesalahan internal saat transfer. Dana Anda aman.', 'danger')
            return redirect(url_for('main.transfer'))

    return render_template(
        'transfer.html', 
        title='Transfer Saldo', 
        form=form, 
        payer_fee_percent=current_app.config['PAYER_FEE_TRANSFER_PERCENT']
    )

@main_bp.route('/pay/<signed_payment_id>', methods=['GET', 'POST'])
@login_required
def pay_page(signed_payment_id):
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    try:
        payment_id = serializer.loads(signed_payment_id, salt='payment-url-salt', max_age=600)
    except (SignatureExpired, BadTimeSignature):
        flash('Link pembayaran tidak valid atau sudah kedaluwarsa.', 'danger')
        return redirect(url_for('main.home'))

    payment = Payment.query.filter_by(payment_id=payment_id, status='PENDING').first_or_404()

    if current_user.id == payment.merchant_id:
        flash('Anda tidak bisa membayar ke diri Anda sendiri.', 'warning')
        return redirect(url_for('main.dashboard'))

    # --- New Fee Calculation Logic ---
    base_amount = payment.amount
    
    if payment.payment_method == 'QR':
        payer_fee_percent = current_app.config['PAYER_FEE_QR_PERCENT']
    else: # Default to LINK
        payer_fee_percent = current_app.config['PAYER_FEE_LINK_PERCENT']
        
    payer_fee = int(base_amount * payer_fee_percent)
    total_debited = base_amount + payer_fee
    
    form = PayPageForm()
    if form.validate_on_submit():
        if not current_user.pin_hash:
            flash('Anda belum mengatur PIN keamanan. Silakan atur di dashboard.', 'warning')
            return redirect(url_for('main.set_pin', next=request.url))
        
        if not bcrypt.check_password_hash(current_user.pin_hash, form.pin.data):
            flash('PIN yang Anda masukkan salah.', 'danger')
            return render_template('pay_page.html', title='Konfirmasi Pembayaran', payment=payment, form=form, payer_fee=payer_fee, total_debited=total_debited)

        try:
            # Lock rows for update
            payer = db.session.query(User).filter_by(id=current_user.id).with_for_update().one()
            merchant = db.session.query(User).filter_by(id=payment.merchant_id).with_for_update().one()
            admin_user = db.session.query(User).filter_by(email='sistem@gabutpay.com').with_for_update().one()

            if payer.balance < total_debited:
                flash('Saldo Anda tidak mencukupi untuk membayar beserta biaya layanan.', 'danger')
                db.session.rollback()
                return render_template('pay_page.html', title='Konfirmasi Pembayaran', payment=payment, form=form, payer_fee=payer_fee, total_debited=total_debited)

            # Calculate merchant fee
            merchant_fee = int(base_amount * current_app.config['MERCHANT_FEE_PERCENT'])
            merchant_amount = base_amount - merchant_fee

            # Update balances
            payer.balance -= total_debited
            merchant.balance += merchant_amount
            admin_user.balance += payer_fee + merchant_fee
            
            # Update payment record with fees and status
            payment.status = 'PAID'
            payment.payer_id = payer.id
            payment.paid_at = datetime.utcnow()
            payment.payer_fee = payer_fee
            payment.merchant_fee = merchant_fee

            api_key = APIKey.query.filter_by(user_id=merchant.id).first()
            store_name = api_key.store_name if api_key else merchant.email

            # Create transaction records
            # Payer side
            payer_tx_1 = Transaction(user_id=payer.id, payment_id=payment.id, transaction_type='PAYMENT_OUT', amount=-base_amount, description=f'Pembayaran ke {store_name}', counterparty_id=merchant.id)
            payer_tx_2 = Transaction(user_id=payer.id, payment_id=payment.id, transaction_type='PAYER_FEE', amount=-payer_fee, description=f'Biaya layanan pembayaran ke {store_name}', counterparty_id=admin_user.id)
            # Merchant side
            merchant_tx = Transaction(user_id=merchant.id, payment_id=payment.id, transaction_type='PAYMENT_IN', amount=merchant_amount, description=f'Pembayaran dari {payer.email}', counterparty_id=payer.id)
            # Admin side
            admin_tx_1 = Transaction(user_id=admin_user.id, payment_id=payment.id, transaction_type='ADMIN_FEE', amount=merchant_fee, description=f'Biaya admin dari pembayaran (sisi merchant: {merchant.email})')
            admin_tx_2 = Transaction(user_id=admin_user.id, payment_id=payment.id, transaction_type='ADMIN_FEE', amount=payer_fee, description=f'Biaya layanan dari pembayaran (sisi pembayar: {payer.email})')

            db.session.add_all([payer_tx_1, payer_tx_2, merchant_tx, admin_tx_1, admin_tx_2])
            db.session.commit()

            # Send notifications
            try:
                # To merchant
                merchant_payload = { "title": "Pembayaran Diterima", "body": f"Anda menerima sebesar Rp {Decimal(merchant_amount) / 100:,.2f} dari {payer.email}." }
                send_push_notification(merchant.id, merchant_payload)
                # To payer
                payer_payload = { "title": "Pembayaran Berhasil", "body": f"Pembayaran Rp {Decimal(base_amount) / 100:,.2f} ke {store_name} berhasil (Total terpotong: Rp {Decimal(total_debited) / 100:,.2f})." }
                send_push_notification(payer.id, payer_payload)
            except Exception as e:
                current_app.logger.error(f"Failed to send push notification(s) for payment {payment.payment_id}: {e}")

            _send_webhook(payment, api_key)
            flash('Pembayaran berhasil!', 'success')
            
            # --- Patched Redirect Logic ---
            if payment.redirect_url_success:
                return redirect(url_for('main.external_redirect', target_url=payment.redirect_url_success))
            else:
                return redirect(url_for('main.payment_details', payment_id=payment.payment_id))

        except Exception as e:
            db.session.rollback()
            payment.status = 'FAILED'
            db.session.commit()
            current_app.logger.error(f"Error during payment execution for payment_id {payment.payment_id}: {e}")
            flash('Terjadi kesalahan internal saat memproses pembayaran. Dana Anda aman.', 'danger')
            
            # --- Patched Redirect Logic ---
            if payment.redirect_url_failure:
                return redirect(url_for('main.external_redirect', target_url=payment.redirect_url_failure))
            else:
                return redirect(url_for('main.dashboard'))

    return render_template('pay_page.html', title='Konfirmasi Pembayaran', payment=payment, form=form, payer_fee=payer_fee, total_debited=total_debited)

@main_bp.route('/delete-key', methods=['POST'])
@login_required
def delete_key():
    form = DeleteKeyForm()
    if form.validate_on_submit():
        key_to_delete = APIKey.query.get(form.key_id.data)
        if key_to_delete and key_to_delete.user_id == current_user.id:
            db.session.delete(key_to_delete)
            db.session.commit()
            flash('API Key berhasil dihapus.', 'success')
        else:
            flash('Gagal menghapus key. Key tidak ditemukan atau bukan milik Anda.', 'danger')
    else:
        flash('Permintaan tidak valid.', 'danger')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/reset-key', methods=['POST'])
@login_required
def reset_key():
    form = ResetKeyForm()
    if form.validate_on_submit():
        key_to_reset = APIKey.query.get(form.key_id.data)
        if not key_to_reset or key_to_reset.user_id != current_user.id:
            flash('Gagal mereset key. Key tidak ditemukan atau bukan milik Anda.', 'danger')
            return redirect(url_for('main.dashboard'))

        new_secret_key = f'sk_test_{secrets.token_hex(24)}'
        new_webhook_secret = f'whsec_{secrets.token_hex(24)}'

        key_to_reset.secret_key_hash = bcrypt.generate_password_hash(new_secret_key).decode('utf-8')
        key_to_reset.secret_key_encrypted = encrypt_data(new_secret_key.encode('utf-8'))
        key_to_reset.webhook_secret_hash = bcrypt.generate_password_hash(new_webhook_secret).decode('utf-8')
        key_to_reset.webhook_secret_encrypted = encrypt_data(new_webhook_secret.encode('utf-8'))
        db.session.commit()

        flash('API Key berhasil direset! Harap simpan Secret Key dan Webhook Secret baru Anda.', 'success')
        return render_template('display_keys.html',
                               public_key=key_to_reset.public_key,
                               secret_key=new_secret_key,
                               webhook_secret=new_webhook_secret,
                               title='Kunci API Telah Direset')
    else:
        flash('Permintaan tidak valid.', 'danger')
    return redirect(url_for('main.dashboard'))

@main_bp.route('/edit-key/<int:key_id>', methods=['GET', 'POST'])
@login_required
def edit_key(key_id):
    api_key = APIKey.query.get_or_404(key_id)
    if api_key.user_id != current_user.id:
        abort(403)

    form = EditKeyForm(obj=api_key)
    if form.validate_on_submit():
        api_key.webhook_url = form.webhook_url.data
        db.session.commit()
        flash('URL Webhook berhasil diperbarui!', 'success')
        return redirect(url_for('main.dashboard'))
    return render_template('edit_key.html', title='Edit API Key', api_key=api_key, form=form)

# --- Split Bill Flow ---

@main_bp.route('/split-bill/create', methods=['GET', 'POST'])
@login_required
def create_split_bill():
    form = SplitBillForm()
    # Add current user's email to the list of participants by default on GET
    if request.method == 'GET' and not form.participants.entries:
        form.participants.append_entry(data=current_user.email)

    if form.validate_on_submit():
        title = form.title.data
        description = form.description.data
        total_in_cents = int(form.total_amount.data * 100)
        
        # Sanitize participant emails: get unique, non-empty emails
        participant_emails = {email.lower() for email in form.participants.data if email}
        # Ensure the creator is in the set
        participant_emails.add(current_user.email.lower())

        num_participants = len(participant_emails)
        if num_participants == 0:
            flash('Tidak ada peserta yang valid.', 'danger')
            return render_template('create_split_bill.html', title='Buat Tagihan Patungan', form=form)

        # Calculate amounts
        base_amount = total_in_cents // num_participants
        remainder = total_in_cents % num_participants

        try:
            # Create the main split bill record
            new_split_bill = SplitBill(
                title=title,
                description=description,
                total_amount=total_in_cents,
                creator_id=current_user.id
            )
            db.session.add(new_split_bill)

            # Pre-fetch user data for existing participants to be efficient
            existing_users = {user.email: user.id for user in User.query.filter(User.email.in_(participant_emails)).all()}

            # Create participant records
            for email in participant_emails:
                amount_due = base_amount
                # Assign remainder to the creator
                if email == current_user.email.lower():
                    amount_due += remainder
                
                participant = SplitBillParticipant(
                    split_bill=new_split_bill,
                    participant_email=email,
                    participant_user_id=existing_users.get(email),
                    amount_due=amount_due
                )
                db.session.add(participant)

            db.session.commit()
            
            # TODO: Send notifications to participants
            
            flash('Tagihan patungan berhasil dibuat!', 'success')
            # TODO: Redirect to the new split bill detail page
            return redirect(url_for('main.dashboard'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error creating split bill: {e}")
            flash('Terjadi kesalahan internal saat membuat tagihan. Harap coba lagi.', 'danger')

    return render_template('create_split_bill.html', title='Buat Tagihan Patungan', form=form)



@main_bp.route('/split-bills')
@login_required
def list_split_bills():
    # A query to get all bill IDs where the user is the creator
    created_bills_q = db.session.query(SplitBill.id).filter(SplitBill.creator_id == current_user.id)

    # A query to get all bill IDs where the user is a participant
    participated_bills_q = db.session.query(SplitBillParticipant.split_bill_id).filter(SplitBillParticipant.participant_user_id == current_user.id)

    # Combine the IDs and remove duplicates
    all_bill_ids = created_bills_q.union(participated_bills_q).subquery()

    # Fetch the actual bill objects
    bills = SplitBill.query.filter(SplitBill.id.in_(all_bill_ids)).order_by(SplitBill.created_at.desc()).all()
    
    return render_template('split_bills_list.html', bills=bills, title="Tagihan Patungan Saya")


@main_bp.route('/split-bill/<int:bill_id>')
@login_required
def split_bill_detail(bill_id):
    bill = SplitBill.query.get_or_404(bill_id)
    
    # Security check: ensure current user is part of this bill
    participant_ids = [p.participant_user_id for p in bill.participants]
    if current_user.id != bill.creator_id and current_user.id not in participant_ids:
        from flask import abort
        abort(403)

    return render_template('split_bill_detail.html', bill=bill, title=f"Detail Tagihan: {bill.title}")


@main_bp.route('/split-bill/pay/<int:participant_id>', methods=['POST'])
@login_required
def pay_split_bill_participant(participant_id):
    participant = SplitBillParticipant.query.get_or_404(participant_id)
    bill = participant.split_bill

    # Security & State Checks
    if participant.participant_user_id != current_user.id:
        from flask import abort
        abort(403) # Can't pay for someone else
    if participant.status != 'PENDING':
        flash('Tagihan ini sudah lunas atau sedang diproses.', 'warning')
        return redirect(url_for('main.split_bill_detail', bill_id=bill.id))
    if bill.status != 'ACTIVE':
        flash('Sesi patungan ini sudah tidak aktif.', 'warning')
        return redirect(url_for('main.split_bill_detail', bill_id=bill.id))

    # TODO: Add PIN authorization form/modal for better security

    try:
        payer = db.session.query(User).filter_by(id=current_user.id).with_for_update().one()
        creator = db.session.query(User).filter_by(id=bill.creator_id).with_for_update().one()

        if payer.balance < participant.amount_due:
            flash('Saldo Anda tidak mencukupi untuk membayar tagihan ini.', 'danger')
            db.session.rollback()
            return redirect(url_for('main.split_bill_detail', bill_id=bill.id))

        # Perform the transfer
        payer.balance -= participant.amount_due
        creator.balance += participant.amount_due

        # Update participant status
        participant.status = 'PAID'

        # Create transaction records
        payer_tx = Transaction(
            user_id=payer.id,
            transaction_type='SPLIT_BILL_OUT',
            amount=-participant.amount_due,
            description=f"Bayar patungan: '{bill.title}'",
            counterparty_id=creator.id
        )
        creator_tx = Transaction(
            user_id=creator.id,
            transaction_type='SPLIT_BILL_IN',
            amount=participant.amount_due,
            description=f"Terima patungan dari {payer.email} untuk '{bill.title}'",
            counterparty_id=payer.id
        )
        db.session.add_all([payer_tx, creator_tx])
        
        # Check if the whole bill is completed
        all_paid = all(p.status == 'PAID' for p in bill.participants)
        if all_paid:
            bill.status = 'COMPLETED'
        
        db.session.commit()

        flash('Pembayaran patungan berhasil!', 'success')

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error paying split bill participant {participant_id}: {e}")
        flash('Terjadi kesalahan internal saat pembayaran.', 'danger')

    return redirect(url_for('main.split_bill_detail', bill_id=bill.id))


@main_bp.route('/split-bill/delete/<int:bill_id>', methods=['POST'])
@login_required
def delete_split_bill(bill_id):
    bill = SplitBill.query.get_or_404(bill_id)
    if bill.creator_id != current_user.id:
        from flask import abort
        abort(403)
    
    if any(p.status == 'PAID' for p in bill.participants):
        flash('Tidak bisa membatalkan tagihan yang sudah ada pembayaran.', 'danger')
        return redirect(url_for('main.split_bill_detail', bill_id=bill.id))

    try:
        db.session.delete(bill)
        db.session.commit()
        flash('Tagihan patungan berhasil dibatalkan.', 'success')
        return redirect(url_for('main.list_split_bills'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting split bill {bill_id}: {e}")
        flash('Gagal membatalkan tagihan.', 'danger')
        return redirect(url_for('main.split_bill_detail', bill_id=bill.id))


@main_bp.route('/split-bill/leave/<int:participant_id>', methods=['POST'])
@login_required
def leave_split_bill(participant_id):
    participant = SplitBillParticipant.query.get_or_404(participant_id)
    bill_id = participant.split_bill_id

    if participant.participant_user_id != current_user.id:
        from flask import abort
        abort(403)
    
    if participant.status == 'PAID':
        flash('Anda tidak bisa keluar dari tagihan yang sudah Anda bayar.', 'warning')
        return redirect(url_for('main.split_bill_detail', bill_id=bill_id))

    if participant.split_bill.creator_id == current_user.id:
        flash('Pembuat tagihan tidak bisa keluar, hanya bisa membatalkan.', 'warning')
        return redirect(url_for('main.split_bill_detail', bill_id=bill_id))

    try:
        db.session.delete(participant)
        db.session.commit()
        flash('Anda telah berhasil keluar dari tagihan patungan.', 'success')
        return redirect(url_for('main.list_split_bills'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error leaving split bill for participant {participant_id}: {e}")
        flash('Gagal keluar dari tagihan.', 'danger')
        return redirect(url_for('main.split_bill_detail', bill_id=bill_id))




# --- QR Code Payment Flow ---

@main_bp.route('/request-payment', methods=['GET', 'POST'])
@login_required
def request_payment():
    form = RequestQRForm()
    if form.validate_on_submit():
        amount_in_cents = int(form.amount.data * 100)
        
        # Create a new Payment record
        new_payment = Payment(
            merchant_id=current_user.id,
            amount=amount_in_cents,
            payment_method='QR', # Set payment method for QR
            merchant_order_id=f'qr_{secrets.token_hex(8)}' # Generate a unique order ID
        )
        db.session.add(new_payment)
        db.session.commit()
        
        return redirect(url_for('main.show_qr', payment_id=new_payment.payment_id))
        
    return render_template('request_payment.html', title='Buat Pembayaran QR', form=form)

@main_bp.route('/show-qr/<payment_id>')
def show_qr(payment_id):
    payment = Payment.query.filter_by(payment_id=payment_id).first_or_404()
    
    # For now, only pending payments can be displayed as a QR
    if payment.status != 'PENDING':
        flash('Pembayaran ini sudah tidak valid.', 'warning')
        return redirect(url_for('main.dashboard'))

    try:
        qr_code_data_uri = generate_qr_code(payment)
    except Exception as e:
        current_app.logger.error(f"Gagal membuat QR code untuk payment_id {payment.payment_id}: {e}")
        flash('Gagal membuat QR code. Harap coba lagi.', 'danger')
        return redirect(url_for('main.request_payment'))

    return render_template('show_qr.html', title='Bayar dengan QR', payment=payment, qr_code=qr_code_data_uri)

@main_bp.route('/scan-qr')
@login_required
def scan_qr():
    return render_template('scan_qr.html', title='Pindai Kode QR')

@main_bp.route('/payment/details/<payment_id>')
@login_required
def payment_details(payment_id):
    payment = Payment.query.filter_by(payment_id=payment_id).first_or_404()
    
    # Security check: only payer or merchant can view the details
    if current_user.id not in [payment.payer_id, payment.merchant_id]:
        abort(403)
        
    return render_template('payment_details.html', title='Detail Pembayaran', payment=payment)

@main_bp.route('/redirect')
def external_redirect():
    from urllib.parse import urlparse
    target_url = request.args.get('target_url')
    if not target_url:
        return redirect(url_for('main.dashboard'))
    
    parsed_url = urlparse(target_url)
    if not parsed_url.scheme in ['http', 'https'] or not parsed_url.netloc:
        flash('URL tujuan tidak valid atau tidak aman.', 'danger')
        return redirect(url_for('main.dashboard'))

    return render_template('redirect_page.html', title='Mengarahkan...', target_url=target_url)


# --- Static & Info Pages ---

@main_bp.route('/offline')
def offline():
    return render_template('offline.html', title='Offline')

@main_bp.route('/terms')
def terms():
    return render_template('static_page.html', title='Terms of Service', 
                           subtitle='Aturan dan Kondisi Penggunaan Layanan GabutPay.',
                           content='''
                                <h4>1. Penerimaan Persyaratan</h4>
                                <p>Dengan menggunakan layanan GabutPay ("Layanan"), Anda setuju untuk terikat oleh Syarat dan Ketentuan ini. Layanan ini adalah <strong>proyek simulasi</strong> untuk tujuan portfolio dan demonstrasi, dan tidak boleh digunakan untuk transaksi keuangan nyata.</p>
                                
                                <h4>2. Deskripsi Layanan</h4>
                                <p>GabutPay menyediakan platform e-wallet dan payment gateway simulasi. Semua saldo, transaksi, dan data adalah fiktif dan hanya ada dalam lingkup aplikasi ini. Tidak ada uang nyata yang terlibat.</p>
                                
                                <h4>3. Akun Pengguna</h4>
                                <p>Anda bertanggung jawab untuk menjaga kerahasiaan informasi akun Anda, termasuk password dan PIN. Aplikasi ini tidak bertanggung jawab atas kehilangan saldo simulasi akibat kelalaian pengguna.</p>
                                
                                <h4>4. Penggunaan yang Dilarang</h4>
                                <p>Anda setuju untuk tidak menggunakan Layanan untuk aktivitas ilegal atau untuk menguji kerentanan keamanan tanpa izin. Setiap upaya penyalahgunaan akan mengakibatkan pemblokiran akun.</p>
                                
                                <h4>5. Batasan Tanggung Jawab</h4>
                                <p>Layanan ini disediakan "sebagaimana adanya" tanpa jaminan apa pun. Pengembang tidak bertanggung jawab atas kehilangan data atau kerusakan apa pun yang mungkin timbul dari penggunaan aplikasi simulasi ini.</p>
                           ''')

@main_bp.route('/privacy')
def privacy():
    return render_template('static_page.html', title='Privacy Policy', 
                           subtitle='Bagaimana kami mengumpulkan, menggunakan, dan melindungi data Anda.',
                           content='''
                                <h4>1. Informasi yang Kami Kumpulkan</h4>
                                <ul>
                                    <li><strong>Informasi Akun:</strong> Kami menyimpan alamat email dan hash dari password serta PIN Anda.</li>
                                    <li><strong>Data Transaksi:</strong> Semua riwayat transaksi fiktif Anda (transfer, pembayaran, pembelian API key) dicatat dalam sistem.</li>
                                    <li><strong>Data Teknis:</strong> Kami menyimpan alamat IP Anda saat registrasi untuk keperluan fitur bonus pendaftaran unik.</li>
                                </ul>
                                
                                <h4>2. Bagaimana Kami Menggunakan Informasi Anda</h4>
                                <p>Data yang dikumpulkan hanya digunakan untuk fungsionalitas inti dari aplikasi simulasi ini, seperti otentikasi, menampilkan riwayat transaksi, dan logika bisnis internal. Kami tidak membagikan data Anda kepada pihak ketiga mana pun.</p>
                                
                                <h4>3. Keamanan Data</h4>
                                <p>Kami menggunakan hashing (bcrypt) untuk mengamankan password dan PIN Anda. Namun, perlu diingat bahwa ini adalah aplikasi simulasi dan tidak boleh digunakan untuk menyimpan data sensitif.</p>
                           ''')

@main_bp.route('/disclaimer')
def disclaimer():
    return render_template('static_page.html', title='Disclaimer', 
                           subtitle='Pernyataan sanggahan penting.',
                           content='''
                                <p class="fs-5">Layanan GabutPay adalah <strong>proyek non-komersial</strong> yang dibuat untuk tujuan pendidikan dan portofolio.</p>
                                <p>Ini adalah <strong>SIMULASI</strong> dan <strong>BUKAN PRODUK KEUANGAN NYATA</strong>. Jangan pernah menggunakan informasi pribadi yang sensitif, password dunia nyata, atau mengharapkan adanya nilai moneter dari saldo yang ditampilkan.</p>
                                <p>Pengembang tidak bertanggung jawab atas kesalahpahaman, kehilangan data, atau masalah apa pun yang timbul dari penggunaan aplikasi ini. Gunakan dengan risiko Anda sendiri.</p>
                           ''')

@main_bp.route('/security')
def security():
    return render_template('static_page.html', title='Security Statement', 
                           subtitle='Bagaimana kami mengamankan platform simulasi kami.',
                           content='''
                                <p>Meskipun GabutPay adalah platform simulasi, kami menerapkan beberapa praktik keamanan standar sebagai bagian dari demonstrasi:</p>
                                <ul>
                                    <li><strong>Hashing Kredensial:</strong> Password dan PIN Keamanan di-hash menggunakan algoritma bcrypt, sehingga kami tidak pernah menyimpan kredensial Anda dalam bentuk teks biasa.</li>
                                    <li><strong>Verifikasi Email (OTP):</strong> Pendaftaran akun baru memerlukan verifikasi melalui One-Time Password (OTP) yang dikirim ke email untuk memastikan kepemilikan email.</li>
                                    <li><strong>Otentikasi Transaksi:</strong> Setiap transaksi sensitif seperti transfer atau pembuatan API key memerlukan otorisasi menggunakan PIN.</li>
                                    <li><strong>Proteksi API:</strong> Endpoint API untuk merchant diamankan menggunakan HMAC-SHA256 signature untuk memastikan integritas dan otentikasi permintaan.</li>
                                    <li><strong>Kebijakan Keamanan Konten (CSP):</strong> Kami menerapkan header CSP untuk mengurangi risiko serangan Cross-Site Scripting (XSS).</li>
                                </ul>
                                <p class="mt-4">Perlu diingat, ini adalah langkah-langkah dasar dan dalam aplikasi keuangan nyata, lapisan keamanan akan jauh lebih kompleks.</p>
                           ''')

@main_bp.route('/docs')
def docs():
    return render_template('static_page.html', title='Dokumentasi API GabutPay', 
                           subtitle='Panduan teknis untuk mengintegrasikan API pembayaran GabutPay.',
                           content='''
                                <h3 id="pendahuluan">Pendahuluan</h3>
                                <p>Selamat datang di dokumentasi API GabutPay. API ini memungkinkan Anda sebagai merchant untuk membuat permintaan pembayaran (<em>payment request</em>) dan menerima notifikasi status pembayaran secara terprogram. Seluruh komunikasi dengan API menggunakan format JSON.</p>
                                <p>Base URL untuk semua endpoint API adalah: <code>https://gabutpay.com/api/v1</code></p>
                                
                                <hr class="my-4">

                                <h3 id="otentikasi">1. Otentikasi Permintaan</h3>
                                <p>Setiap permintaan yang dikirim ke API GabutPay harus diotentikasi menggunakan <strong>Request Signature</strong>. Hal ini untuk memastikan bahwa permintaan benar-benar berasal dari Anda dan integritas datanya terjaga selama transmisi.</p>
                                <p>Signature dibuat menggunakan algoritma <strong>HMAC-SHA256</strong>.</p>
                                
                                <h4>Langkah-langkah Pembuatan Signature:</h4>
                                <ol>
                                    <li>
                                        <strong>Siapkan String-to-Sign:</strong> Gabungkan tiga komponen berikut:
                                        <ul>
                                            <li>Unix Timestamp saat ini (dalam format string).</li>
                                            <li>Karakter titik (<code>.</code>).</li>
                                            <li>Body dari request Anda dalam format JSON mentah (<em>raw JSON string</em>), tanpa spasi ekstra.</li>
                                        </ul>
                                        <p>Format: <code>{TIMESTAMP}.{RAW_JSON_BODY}</code></p>
                                    </li>
                                    <li>
                                        <strong>Buat Signature:</strong> Gunakan algoritma HMAC-SHA256 untuk mengenkripsi <em>String-to-Sign</em> dari langkah pertama. Gunakan <strong>Secret Key</strong> Anda sebagai kunci enkripsi. Hasilnya harus dalam format heksadesimal (<em>hex digest</em>).
                                    </li>
                                </ol>

                                <h4>Header yang Wajib Disertakan:</h4>
                                <p>Setiap permintaan ke API harus menyertakan tiga (3) header berikut:</p>
                                <ul>
                                    <li><code>X-PUBLIC-KEY</code>: Berisi Public Key Anda.</li>
                                    <li><code>X-REQUEST-TIMESTAMP</code>: Unix timestamp yang sama dengan yang Anda gunakan untuk membuat signature. Permintaan akan ditolak jika timestamp lebih tua dari 60 detik untuk mencegah <em>replay attack</em>.</li>
                                    <li><code>X-SIGNATURE</code>: Hasil signature dari langkah-langkah di atas.</li>
                                </ul>

                                <hr class="my-4">

                                <h3 id="endpoint-create-payment">2. Endpoint: Buat Pembayaran</h3>
                                <p>Endpoint ini digunakan untuk membuat sebuah sesi pembayaran baru. Jika berhasil, API akan mengembalikan sebuah <code>payment_url</code> yang dapat Anda teruskan kepada pelanggan untuk melakukan pembayaran.</p>
                                
                                <h5><code>POST /api/v1/create-payment</code></h5>
                                
                                <h4>Body Request (JSON)</h4>
                                <table class="table table-bordered">
                                    <thead>
                                        <tr>
                                            <th>Parameter</th>
                                            <th>Tipe</th>
                                            <th>Wajib</th>
                                            <th>Deskripsi</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        <tr>
                                            <td><code>amount</code></td>
                                            <td>Integer</td>
                                            <td>Ya</td>
                                            <td>Jumlah pembayaran dalam satuan <strong>sen</strong>. Contoh: <code>50000</code> untuk Rp 500,00.</td>
                                        </tr>
                                        <tr>
                                            <td><code>merchant_order_id</code></td>
                                            <td>String</td>
                                            <td>Ya</td>
                                            <td>ID unik untuk pesanan di sistem Anda. Digunakan untuk rekonsiliasi.</td>
                                        </tr>
                                        <tr>
                                            <td><code>description</code></td>
                                            <td>String</td>
                                            <td>Opsional</td>
                                            <td>Deskripsi singkat pembayaran yang akan ditampilkan ke pelanggan.</td>
                                        </tr>
                                        <tr>
                                            <td><code>payment_method</code></td>
                                            <td>String</td>
                                            <td>Opsional</td>
                                            <td>Metode pembayaran yang diinginkan. Bisa diisi <code>'link'</code> (default) untuk mendapatkan URL pembayaran, atau <code>'qr'</code> untuk mendapatkan data URI dari gambar QR code.</td>
                                        </tr>
                                        <tr>
                                            <td><code>redirect_url_success</code></td>
                                            <td>String</td>
                                            <td>Opsional</td>
                                            <td>URL tujuan untuk mengalihkan pelanggan jika pembayaran berhasil (hanya berlaku untuk metode 'link').</td>
                                        </tr>
                                        <tr>
                                            <td><code>redirect_url_failure</code></td>
                                            <td>String</td>
                                            <td>Opsional</td>
                                            <td>URL tujuan untuk mengalihkan pelanggan jika pembayaran gagal (hanya berlaku untuk metode 'link').</td>
                                        </tr>
                                    </tbody>
                                </table>

                                <h4>Contoh Response Sukses (Metode 'link')</h4>
                                <pre class="bg-dark text-light p-3 rounded"><code>
{
    "message": "Payment created successfully",
    "payment_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
    "payment_url": "https://gabutpay.com/pay/..."
}
                                </code></pre>

                                <h4>Contoh Response Sukses (Metode 'qr')</h4>
                                <pre class="bg-dark text-light p-3 rounded"><code>
{
    "message": "Payment QR code created successfully",
    "payment_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
    "qr_code_data_uri": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg..."
}
                                </code></pre>

                                <hr class="my-4">

                                <h3 id="webhook">3. Notifikasi Webhook</h3>
                                <p>Jika Anda mengatur URL Webhook di dashboard, sistem kami akan mengirimkan notifikasi dengan metode <code>POST</code> ke URL tersebut setiap kali status pembayaran berubah (misalnya, dari <code>PENDING</code> menjadi <code>PAID</code>).</p>
                                <p>Untuk memverifikasi bahwa webhook berasal dari GabutPay, setiap request webhook akan menyertakan header <code>X-GABUTPAY-SIGNATURE</code>. Signature ini dibuat dengan mengenkripsi body mentah dari webhook menggunakan algoritma HMAC-SHA256 dan <strong>Webhook Secret</strong> Anda sebagai kuncinya.</p>
                                
                                <h4>Contoh Payload Webhook</h4>
                                <pre class="bg-dark text-light p-3 rounded"><code>
{
    "payment_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
    "merchant_order_id": "INV-2025-001",
    "status": "PAID",
    "amount": 50000,
    "paid_at": "2025-11-21T14:30:00Z"
}
                                </code></pre>

                                <hr class="my-4">

                                <h3 id="contoh-kode">4. Contoh Kode Otentikasi</h3>
                                <p>Berikut adalah contoh implementasi pembuatan signature dalam bahasa Python dan Node.js.</p>

                                <h4>Python</h4>
                                <pre class="bg-dark text-light p-3 rounded"><code>
import hmac
import hashlib
import time
import json
import requests

# --- Konfigurasi Anda ---
SECRET_KEY = "sk_test_anda..."
PUBLIC_KEY = "pk_test_anda..."
BASE_URL = "https://gabutpay.com/api/v1" # Ganti jika URL berbeda

# --- Data Pembayaran ---
payload = {
    "amount": 50000,
    "merchant_order_id": "INV-2025-001",
    "description": "Pembelian item premium"
}
# Pastikan JSON di-serialize tanpa spasi
raw_body = json.dumps(payload, separators=(',', ':')).encode('utf-8')

# --- Buat Signature ---
timestamp = str(int(time.time()))
string_to_sign = f"{timestamp}.".encode('utf-8') + raw_body

signature = hmac.new(
    SECRET_KEY.encode('utf-8'),
    string_to_sign,
    hashlib.sha256
).hexdigest()

# --- Kirim Request ---
headers = {
    'Content-Type': 'application/json',
    'X-PUBLIC-KEY': PUBLIC_KEY,
    'X-REQUEST-TIMESTAMP': timestamp,
    'X-SIGNATURE': signature
}

try:
    response = requests.post(
        f"{BASE_URL}/create-payment",
        headers=headers,
        data=raw_body,
        timeout=10
    )
    response.raise_for_status()
    print("Response JSON:", response.json())

except requests.exceptions.RequestException as e:
    print(f"Error: {e}")
    if e.response:
        print("Error Body:", e.response.text)

                                </code></pre>

                                <h4>Node.js (JavaScript)</h4>
                                <pre class="bg-dark text-light p-3 rounded"><code>
const crypto = require('crypto');
const https = require('https');

// --- Konfigurasi Anda ---
const SECRET_KEY = 'sk_test_anda...';
const PUBLIC_KEY = 'pk_test_anda...';
const BASE_URL = 'gabutpay.com'; // Ganti jika URL berbeda

// --- Data Pembayaran ---
const payload = {
    amount: 50000,
    merchant_order_id: 'INV-2025-002',
    description: 'Pembelian item premium'
};
// Pastikan JSON di-serialize tanpa spasi
const rawBody = JSON.stringify(payload);

// --- Buat Signature ---
const timestamp = Math.floor(Date.now() / 1000).toString();
const stringToSign = `${timestamp}.${rawBody}`;

const signature = crypto
    .createHmac('sha256', SECRET_KEY)
    .update(stringToSign)
    .digest('hex');

// --- Kirim Request ---
const options = {
    hostname: BASE_URL,
    path: '/api/v1/create-payment',
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'Content-Length': rawBody.length,
        'X-PUBLIC-KEY': PUBLIC_KEY,
        'X-REQUEST-TIMESTAMP': timestamp,
        'X-SIGNATURE': signature
    }
};

const req = https.request(options, (res) => {
    let data = '';
    res.on('data', (chunk) => {
        data += chunk;
    });
    res.on('end', () => {
        console.log(`Status Code: ${res.statusCode}`);
        try {
            console.log('Response JSON:', JSON.parse(data));
        } catch (e) {
            console.error('Failed to parse JSON response:', data);
        }
    });
});

req.on('error', (error) => {
    console.error('Error:', error);
});

req.write(rawBody);
req.end();

                                </code></pre>
                           ''')

@main_bp.route('/changelog')
def changelog():
    return render_template('static_page.html', title='Changelog', 
                           subtitle='Catatan perubahan dan versi aplikasi.',
                           content='''
                                <h4 class="mb-3">Versi 1.1.0</h4>
                                <ul>
                                    <li><strong>Fitur Mayor: Sistem Pembayaran QR Code</strong>
                                        <ul>
                                            <li>User kini bisa membuat permintaan pembayaran via QR code dinamis dari menu "Minta Bayar".</li>
                                            <li>Menambahkan halaman scanner QR (/scan-qr) yang bisa menggunakan kamera atau memilih file dari galeri.</li>
                                            <li>API untuk merchant kini mendukung pembuatan QR code on-demand via parameter <code>payment_method: 'qr'</code>.</li>
                                        </ul>
                                    </li>
                                    <li><strong>Fitur Mayor: Halaman Detail Transaksi (Struk Digital)</strong>
                                        <ul>
                                            <li>Membuat halaman detail untuk setiap event pembayaran, dapat diakses setelah pembayaran sukses atau dari riwayat.</li>
                                            <li>Menyatukan alur pembayaran (Transfer & QR) ke dalam satu model data `Payment` yang terpadu.</li>
                                            <li>Halaman riwayat transaksi kini interaktif dan bisa di-klik untuk melihat detail.</li>
                                        </ul>
                                    </li>
                                    <li><strong>Perombakan Backend & Keamanan</strong>
                                        <ul>
                                            <li>Mengganti database dari SQLite ke arsitektur yang mendukung PostgreSQL.</li>
                                            <li>Mengimplementasikan sistem migrasi database menggunakan Flask-Migrate.</li>
                                            <li>Menghapus semua nilai hardcoded (biaya admin, dll) dan memindahkannya ke environment variable.</li>
                                            <li>Memperketat Content Security Policy (CSP) secara signifikan dengan menghapus semua script dan style inline.</li>
                                            <li>Memperbaiki berbagai bug terkait tampilan input PIN, fungsi copy, dan masalah environment server.</li>
                                        </ul>
                                    </li>
                                </ul>
                                <hr>
                                <h4>Versi 1.0.0</h4>
                                <ul>
                                    <li>Peluncuran awal platform GabutPay.</li>
                                    <li>Fitur dasar: registrasi, login, transfer, dan manajemen saldo.</li>
                                    <li>Fitur merchant: pembuatan API Key dan endpoint untuk membuat pembayaran via link.</li>
                                    <li>Panel admin dasar untuk manajemen pengguna.</li>
                                </ul>
                           ''')

@main_bp.route('/support')
def support():
    return render_template('static_page.html', title='Support / Help Center', 
                           subtitle='Butuh bantuan? Cari di sini.',
                           content='''
                                <p>GabutPay adalah proyek simulasi. Dukungan teknis sangat terbatas.</p>
                                <p>Jika Anda menemukan bug, kesalahan, atau memiliki masukan, cara terbaik untuk menghubungi kami adalah melalui halaman <a href="{{ url_for('main.bug_report') }}">Lapor Bug</a>.</p>
                                <p>Untuk pertanyaan umum tentang cara kerja aplikasi, silakan merujuk ke <a href="{{ url_for('main.docs') }}">Dokumentasi API</a>.</p>
                           ''')

@main_bp.route('/credits')
def credits():
    return render_template('static_page.html', title='Attribution / Credits', 
                           subtitle='Aplikasi ini adalah hasil kolaborasi antara manusia dan kecerdasan buatan.',
                           content='''
                                <p>Aplikasi ini dibangun menggunakan teknologi-teknologi hebat berikut:</p>
                                <ul>
                                    <li><strong>Flask:</strong> Kerangka kerja web Python yang menjadi tulang punggung aplikasi.</li>
                                    <li><strong>Bootstrap 5:</strong> Framework CSS untuk membangun antarmuka yang responsif.</li>
                                    <li><strong>SQLAlchemy:</strong> Toolkit SQL dan Object Relational Mapper untuk interaksi database.</li>
                                </ul>
                                <p>Logika, arsitektur, dan sebagian besar kode dalam proyek ini dirancang dan ditulis dengan bantuan model bahasa besar (AI) dari Google. Proyek ini menjadi bukti konsep kolaborasi produktif antara developer dan AI.</p>
                           ''')

@main_bp.route('/bug-report', methods=['GET', 'POST'])
def bug_report():
    form = BugReportForm()
    if form.validate_on_submit():
        subject = form.subject.data
        description = form.description.data
        
        user_info = f"Pengguna: {current_user.email} (ID: {current_user.id})" if current_user.is_authenticated else "Pengguna: Anonim"

        msg = Message(f"Laporan Bug/Feedback: {subject}",
                      sender=current_app.config['MAIL_USERNAME'],
                      recipients=[current_app.config['ADMIN_EMAIL']])
        msg.body = f"Laporan baru diterima.\n\nDari: {user_info}\n\nDeskripsi:\n{description}"
        
        try:
            mail.send(msg)
            flash('Terima kasih! Laporan Anda telah berhasil dikirim.', 'success')
        except Exception as e:
            current_app.logger.error(f"Error sending bug report email: {e}")
            flash('Gagal mengirim laporan. Silakan coba lagi nanti.', 'danger')
        return redirect(url_for('main.home'))
    return render_template('bug_report.html', title='Lapor Bug atau Beri Masukan', form=form)







