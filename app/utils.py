import os
import base64
from cryptography.fernet import Fernet, InvalidToken
import qrcode
import json
import time
import hmac
import hashlib
import io
from flask import current_app

# Load the master encryption key from environment variables
ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY')
if not ENCRYPTION_KEY:
    raise ValueError("No ENCRYPTION_KEY set for Flask application")

# It's good practice to ensure the key is in bytes
key_bytes = ENCRYPTION_KEY.encode()

# Create a Fernet instance
fernet = Fernet(key_bytes)

def encrypt_data(data: bytes) -> str:
    """Encrypts a bytestring and returns a URL-safe string token."""
    if not isinstance(data, bytes):
        raise TypeError("Data to encrypt must be in bytes.")
    return fernet.encrypt(data).decode('utf-8')

def decrypt_data(token: str) -> bytes | None:
    """Decrypts a token string and returns the original bytestring. Returns None if token is invalid or expired."""
    if not isinstance(token, str):
        return None
    try:
        return fernet.decrypt(token.encode('utf-8'))
    except InvalidToken:
        # This handles invalid tokens (tampered with, incorrect padding, etc.)
        return None

def generate_qr_code(payment):
    """Generates a secure, dynamic QR code for a given payment."""
    secret_key = current_app.config['QR_HMAC_SECRET_KEY']
    if not secret_key:
        raise ValueError("QR_HMAC_SECRET_KEY is not configured.")

    # 1. Create the payload
    payload = {
        "txid": payment.payment_id,
        "amount": payment.amount,
        "exp": int(time.time()) + 300  # Expires in 5 minutes
    }
    
    # Sort keys to ensure consistent string for signing
    payload_string = json.dumps(payload, sort_keys=True)

    # 2. Generate HMAC signature
    sig = hmac.new(
        secret_key.encode('utf-8'),
        payload_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()

    # 3. Add signature to the final data
    data_to_encode = {
        "payload": payload,
        "sig": sig
    }
    
    final_data_string = json.dumps(data_to_encode)

    # 4. Generate QR code image in memory
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_L)
    qr.add_data(final_data_string)
    qr.make(fit=True)
    
    img = qr.make_image(fill='black', back_color='white')
    
    # 5. Save image to a buffer and encode as Base64
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode("utf-8")

    return f"data:image/png;base64,{img_str}"
