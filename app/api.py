import hmac
import hashlib
import time
from functools import wraps
from flask import Blueprint, request, jsonify, g, current_app, url_for
from itsdangerous import URLSafeTimedSerializer

from . import db
from .models import APIKey, User, Payment, Transaction
from .utils import decrypt_data, generate_qr_code

api_bp = Blueprint('api', __name__)

# --- DECORATOR UNTUK OTENTIKASI API DENGAN SIGNATURE ---
def require_api_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Ambil semua header yang dibutuhkan
        public_key = request.headers.get('X-PUBLIC-KEY')
        signature_header = request.headers.get('X-SIGNATURE')
        timestamp_header = request.headers.get('X-REQUEST-TIMESTAMP')

        if not all([public_key, signature_header, timestamp_header]):
            return jsonify({"error": "Missing required headers: X-PUBLIC-KEY, X-SIGNATURE, X-REQUEST-TIMESTAMP"}), 401

        # 2. Validasi timestamp untuk mencegah replay attack
        try:
            timestamp = int(timestamp_header)
            current_time = int(time.time())
            if abs(current_time - timestamp) > 60: # Tolak jika request lebih tua dari 60 detik
                return jsonify({"error": "Timestamp is too old"}), 401
        except (ValueError, TypeError):
            return jsonify({"error": "Invalid timestamp format"}), 401

        # 3. Cari API Key berdasarkan public key
        api_key_entry = APIKey.query.filter_by(public_key=public_key).first()
        if not api_key_entry or not api_key_entry.secret_key_encrypted:
            return jsonify({"error": "Invalid Public Key or key not configured for signing"}), 401

        # 4. Dekripsi secret key
        try:
            decrypted_secret_bytes = decrypt_data(api_key_entry.secret_key_encrypted)
            if not decrypted_secret_bytes:
                raise Exception("Decryption returned None")
            secret_key = decrypted_secret_bytes.decode('utf-8')
        except Exception as e:
            current_app.logger.critical(f"Failed to decrypt secret key for public_key {public_key}. Error: {e}")
            return jsonify({"error": "Internal server error during authentication"}), 500

        # 5. Buat ulang signature di sisi server
        raw_body = request.get_data() # Ambil body mentah dari request
        string_to_sign = f"{timestamp_header}.".encode('utf-8') + raw_body
        
        expected_signature = hmac.new(
            secret_key.encode('utf-8'),
            string_to_sign,
            hashlib.sha256
        ).hexdigest()

        # 6. Bandingkan signature dengan aman
        if not hmac.compare_digest(expected_signature, signature_header):
            return jsonify({"error": "Invalid Signature"}), 401

        # Jika semua valid, set merchant di global context dan lanjutkan
        g.merchant = api_key_entry.owner
        return f(*args, **kwargs)
    return decorated_function

@api_bp.route('/create-payment', methods=['POST'])
@require_api_auth
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
