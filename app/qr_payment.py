import time
import hmac
import hashlib
import json
from flask import Blueprint, request, jsonify, current_app, url_for
from .models import Payment
from . import db

qr_payment_bp = Blueprint('qr_payment', __name__)

@qr_payment_bp.route('/verify-qr-payment', methods=['POST'])
def verify_qr_payment():
    """
    Verifies a scanned QR code payload and returns a secure URL 
    to the payment confirmation page.
    """
    data = request.get_json()
    if not data or 'payload' not in data or 'sig' not in data:
        return jsonify({'success': False, 'error': 'Payload tidak lengkap.'}), 400

    payload = data['payload']
    signature = data['sig']

    # 1. Verify HMAC signature
    secret_key = current_app.config['QR_HMAC_SECRET_KEY']
    payload_string = json.dumps(payload, sort_keys=True)
    expected_sig = hmac.new(
        secret_key.encode('utf-8'),
        payload_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_sig, signature):
        return jsonify({'success': False, 'error': 'Signature QR Code tidak valid.'}), 403

    # 2. Check expiration
    if time.time() > payload.get('exp', 0):
        return jsonify({'success': False, 'error': 'QR Code sudah kedaluwarsa.'}), 400

    # 3. Find payment and check status
    payment = Payment.query.filter_by(payment_id=payload.get('txid')).first()
    if not payment:
        return jsonify({'success': False, 'error': 'ID Transaksi tidak ditemukan.'}), 404
    
    if payment.status != 'PENDING':
        return jsonify({'success': False, 'error': f'Status pembayaran ini adalah {payment.status}, tidak bisa diproses.'}), 400

    # 4. Check amount consistency
    if payment.amount != payload.get('amount'):
        return jsonify({'success': False, 'error': 'Jumlah pembayaran tidak cocok.'}), 400

    # 5. All checks passed, generate the secure redirect URL
    redirect_url = url_for('main.pay_page', signed_payment_id=payment.get_signed_id(), _external=True)
    
    return jsonify({'success': True, 'redirect_url': redirect_url})
