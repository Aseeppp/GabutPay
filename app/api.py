import hmac
import hashlib
import time
from functools import wraps
from flask import Blueprint, request, jsonify, g, current_app, url_for
from itsdangerous import URLSafeTimedSerializer
from sqlalchemy import func
from datetime import datetime, date

from . import db
from .models import APIKey, User, Payment, Transaction, InboundLog
from .utils import decrypt_data, generate_qr_code

api_bp = Blueprint('api', __name__)

# --- DECORATOR UNTUK OTENTIKASI API DENGAN SIGNATURE ---
def require_api_auth(inbound_only=False):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # 1. Ambil semua header yang dibutuhkan
            public_key = request.headers.get('X-PUBLIC-KEY')
            signature_header = request.headers.get('X-SIGNATURE')
            timestamp_header = request.headers.get('X-REQUEST-TIMESTAMP')

            if not all([public_key, signature_header, timestamp_header]):
                return jsonify({"error": "Missing required headers"}), 401

            # 2. Validasi timestamp
            try:
                timestamp = int(timestamp_header)
                if abs(int(time.time()) - timestamp) > 60:
                    return jsonify({"error": "Timestamp is too old"}), 401
            except:
                return jsonify({"error": "Invalid timestamp"}), 401

            # 3. Cari API Key
            api_key_entry = APIKey.query.filter_by(public_key=public_key).first()
            if not api_key_entry:
                return jsonify({"error": "Invalid API Key"}), 401

            # --- SECURITY CHECK: INBOUND ONLY ---
            if inbound_only:
                if not api_key_entry.owner.is_partner or not api_key_entry.is_inbound_enabled:
                    return jsonify({"error": "This API Key is not authorized for inbound transfers"}), 403
                
                # --- SECURITY CHECK: IP WHITELISTING ---
                if api_key_entry.allowed_ips:
                    allowed_ips = [ip.strip() for ip in api_key_entry.allowed_ips.split(',')]
                    # Use request.access_route[0] to get real client IP if behind proxy
                    client_ip = request.access_route[0] if request.access_route else request.remote_addr
                    if client_ip not in allowed_ips:
                        current_app.logger.warning(f"Unauthorized IP {client_ip} tried to access Inbound API with key {public_key}")
                        return jsonify({"error": f"IP {client_ip} is not whitelisted"}), 403

            # 4. Validasi Signature (HMAC)
            try:
                decrypted_secret_bytes = decrypt_data(api_key_entry.secret_key_encrypted)
                secret_key = decrypted_secret_bytes.decode('utf-8')
            except:
                return jsonify({"error": "Internal auth error"}), 500

            raw_body = request.get_data()
            string_to_sign = f"{timestamp_header}.".encode('utf-8') + raw_body
            expected_signature = hmac.new(secret_key.encode('utf-8'), string_to_sign, hashlib.sha256).hexdigest()

            if not hmac.compare_digest(expected_signature, signature_header):
                return jsonify({"error": "Invalid Signature"}), 401

            g.merchant = api_key_entry.owner
            g.api_key = api_key_entry
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@api_bp.route('/create-payment', methods=['POST'])
@require_api_auth(inbound_only=False)
def create_payment():
    data = request.get_json()
    if not data or not all(k in data for k in ['amount', 'merchant_order_id']):
        return jsonify({"error": "Missing required fields: amount, merchant_order_id"}), 400

    # Validasi amount
    try:
        amount_in_cents = int(data['amount'])
        if amount_in_cents <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid amount"}), 400

    # --- Generate payment method based on request ---
    payment_method = data.get('payment_method', 'link') # Default to 'link'

    # Buat Payment record di database
    new_payment = Payment(
        merchant_id=g.merchant.id,
        amount=amount_in_cents,
        payment_method=payment_method.upper(), # Store method ('LINK' or 'QR')
        merchant_order_id=data['merchant_order_id'],
        description=data.get('description', ''),
        redirect_url_success=data.get('redirect_url_success'),
        redirect_url_failure=data.get('redirect_url_failure')
    )
    db.session.add(new_payment)
    db.session.commit()

    if payment_method == 'qr':
        try:
            qr_code_uri = generate_qr_code(new_payment)
            return jsonify({
                "message": "Payment QR code created successfully",
                "payment_id": new_payment.payment_id,
                "qr_code_data_uri": qr_code_uri
            }), 201
        except Exception as e:
            current_app.logger.error(f"Failed to generate QR code for payment {new_payment.payment_id}: {e}")
            return jsonify({"error": "Failed to generate QR code"}), 500
    
    # Default to 'link' method
    else:
        payment_url = url_for('main.pay_page', signed_payment_id=new_payment.get_signed_id(), _external=True)
        return jsonify({
            "message": "Payment created successfully",
            "payment_id": new_payment.payment_id,
            "payment_url": payment_url
        }), 201

@api_bp.route('/inbound-transfer', methods=['POST'])
@require_api_auth(inbound_only=True)
def inbound_transfer():
    data = request.get_json()
    if not data or not all(k in data for k in ['amount', 'external_id', 'recipient_email']):
        return jsonify({"error": "Missing required fields: amount, external_id, recipient_email"}), 400

    try:
        amount_in_cents = int(data['amount'])
        if amount_in_cents <= 0:
            raise ValueError()
    except:
        return jsonify({"error": "Invalid amount"}), 400

    external_id = data['external_id']
    recipient_email = data['recipient_email']
    partner_id = g.merchant.id
    api_key_id = g.api_key.id

    try:
        # 1. LOCK API KEY to prevent daily limit race condition
        api_key = db.session.query(APIKey).filter_by(id=api_key_id).with_for_update().one()
        
        # 2. FIND RECIPIENT
        recipient_stub = User.query.filter_by(email=recipient_email).first()
        if not recipient_stub:
            return jsonify({"error": "Recipient user not found"}), 404
        
        if recipient_stub.id == partner_id:
            return jsonify({"error": "Cannot transfer to yourself"}), 400

        # 3. CONSISTENT LOCKING ORDER to prevent Deadlock
        # Always lock the smaller ID first
        if partner_id < recipient_stub.id:
            partner = db.session.query(User).filter_by(id=partner_id).with_for_update().one()
            recipient = db.session.query(User).filter_by(id=recipient_stub.id).with_for_update().one()
        else:
            recipient = db.session.query(User).filter_by(id=recipient_stub.id).with_for_update().one()
            partner = db.session.query(User).filter_by(id=partner_id).with_for_update().one()

        # 4. STRICT IDEMPOTENCY CHECK
        existing_log = InboundLog.query.filter_by(partner_id=partner.id, external_id=external_id).first()
        if existing_log:
            # Verify that the existing record matches the current request
            if existing_log.amount == amount_in_cents and existing_log.recipient_id == recipient.id:
                return jsonify({
                    "message": "Transaction already processed (Idempotent)",
                    "external_id": external_id,
                    "status": existing_log.status,
                    "amount": existing_log.amount
                }), 200
            else:
                return jsonify({"error": "Conflict: external_id already exists with different data"}), 409

        # 5. DAILY LIMIT CHECK (now safe due to APIKey lock)
        today_start = datetime.combine(date.today(), datetime.min.time())
        total_today = db.session.query(func.sum(InboundLog.amount)).filter(
            InboundLog.api_key_id == api_key.id,
            InboundLog.timestamp >= today_start,
            InboundLog.status == 'SUCCESS'
        ).scalar() or 0

        if total_today + amount_in_cents > api_key.daily_limit:
            return jsonify({"error": "Daily inbound limit exceeded for this API Key"}), 403

        # 6. PARTNER BALANCE CHECK
        if partner.balance < amount_in_cents:
            return jsonify({"error": "Insufficient partner balance"}), 403

        # 7. EXECUTE TRANSFER
        partner.balance -= amount_in_cents
        recipient.balance += amount_in_cents
        
        # Create Inbound Log
        client_ip = request.access_route[0] if request.access_route else request.remote_addr
        inbound_log = InboundLog(
            partner_id=partner.id,
            api_key_id=api_key.id,
            recipient_id=recipient.id,
            external_id=external_id,
            amount=amount_in_cents,
            request_ip=client_ip
        )
        db.session.add(inbound_log)

        # Create Transaction records for both sides
        # Recipient side (Credit)
        recipient_tx = Transaction(
            user_id=recipient.id,
            transaction_type='INBOUND_DEPOSIT',
            amount=amount_in_cents,
            description=f"Inbound top up dari {partner.email} (Ref: {external_id})",
            counterparty_id=partner.id
        )
        # Partner side (Debit)
        partner_tx = Transaction(
            user_id=partner.id,
            transaction_type='INBOUND_PAYMENT',
            amount=-amount_in_cents,
            description=f"Inbound payment ke {recipient.email} (Ref: {external_id})",
            counterparty_id=recipient.id
        )
        db.session.add_all([recipient_tx, partner_tx])

        db.session.commit()
        
        current_app.logger.info(f"SUCCESS Inbound: {amount_in_cents} cents from {partner.email} to {recipient_email}")

        return jsonify({
            "success": True,
            "message": "Inbound transfer successful",
            "amount": amount_in_cents,
            "external_id": external_id,
            "recipient": recipient_email
        }), 201

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"FATAL Inbound Error: {e}")
        return jsonify({"error": "Internal server error during transfer"}), 500
