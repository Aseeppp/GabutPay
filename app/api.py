import hmac
import hashlib
import time
from functools import wraps
from flask import Blueprint, request, jsonify, g, current_app, url_for
from itsdangerous import URLSafeTimedSerializer

from . import db
from .models import APIKey, User, Payment

api_bp = Blueprint('api', __name__)

# --- DECORATOR UNTUK OTENTIKASI API ---
def require_api_auth(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        public_key_header = request.headers.get('X-PUBLIC-KEY', '')
        public_key = public_key_header.strip()
        


        if not public_key:
            return jsonify({"error": "X-PUBLIC-KEY header is required"}), 401

        api_key_entry = APIKey.query.filter_by(public_key=public_key).first()
        if not api_key_entry:
            return jsonify({"error": "Invalid Public Key"}), 401

        # In a real app, you would verify the request signature here using the secret key.
        # For this simulation, we are only authenticating based on the public key.
        # This is NOT secure for production.

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

    # Buat Payment record di database
    new_payment = Payment(
        merchant_id=g.merchant.id,
        amount=amount_in_cents,
        merchant_order_id=data['merchant_order_id'],
        description=data.get('description', ''),
        redirect_url_success=data.get('redirect_url_success'),
        redirect_url_failure=data.get('redirect_url_failure')
    )
    db.session.add(new_payment)
    db.session.commit()

    # Buat URL pembayaran yang aman dan berbatas waktu
    serializer = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
    signed_payment_id = serializer.dumps(new_payment.payment_id, salt='payment-url-salt')

    # Kita butuh rute 'main.pay_page' yang akan kita buat nanti
    payment_url = url_for('main.pay_page', signed_payment_id=signed_payment_id, _external=True)

    return jsonify({
        "message": "Payment created successfully",
        "payment_id": new_payment.payment_id,
        "payment_url": payment_url
    }), 201
