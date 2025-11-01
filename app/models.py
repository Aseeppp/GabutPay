import uuid
from flask import current_app
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
from . import db, login_manager
from flask_login import UserMixin
from datetime import datetime

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)
    pin_hash = db.Column(db.String(60), nullable=True) # For PIN
    balance = db.Column(db.Integer, nullable=False, default=0) # For Saldo, stored as cents
    is_verified = db.Column(db.Boolean, nullable=False, default=False) # For email OTP
    otp_hash = db.Column(db.String(60), nullable=True)
    otp_expiry = db.Column(db.DateTime, nullable=True)
    registration_ip = db.Column(db.String(45), nullable=True)
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    banned_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Relationship to APIKey
    api_keys = db.relationship('APIKey', backref='owner', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"User('{self.email}')"

    def get_reset_token(self, expires_sec=1800):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id}, salt='password-reset-salt')

    @staticmethod
    def verify_reset_token(token, expires_sec=1800):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token, salt='password-reset-salt', max_age=expires_sec)
            user_id = data.get('user_id')
        except (SignatureExpired, BadTimeSignature, KeyError):
            return None
        return User.query.get(user_id)

    def get_pin_reset_token(self, expires_sec=1800):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id}, salt='pin-reset-salt')

    @staticmethod
    def verify_pin_reset_token(token, expires_sec=1800):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        try:
            data = s.loads(token, salt='pin-reset-salt', max_age=expires_sec)
            user_id = data.get('user_id')
        except (SignatureExpired, BadTimeSignature, KeyError):
            return None
        return User.query.get(user_id)

class APIKey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    public_key = db.Column(db.String(64), unique=True, nullable=False)
    secret_key_hash = db.Column(db.String(128), nullable=False)
    webhook_secret_hash = db.Column(db.String(128), nullable=False)
    webhook_url = db.Column(db.String(255), nullable=True)
    store_name = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    
    # Foreign Key to link to a User
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"APIKey('{self.public_key}')"

class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    counterparty_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    description = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('transactions', cascade="all, delete-orphan"))
    counterparty = db.relationship('User', foreign_keys=[counterparty_id])

    def __repr__(self):
        return f"Transaction('{self.user.email}', '{self.transaction_type}', {self.amount})"

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    merchant_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    payer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    amount = db.Column(db.Integer, nullable=False) # In cents
    merchant_order_id = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=True)
    redirect_url_success = db.Column(db.String(255), nullable=True)
    redirect_url_failure = db.Column(db.String(255), nullable=True)
    
    status = db.Column(db.String(20), nullable=False, default='PENDING') # PENDING, PAID, FAILED, EXPIRED
    
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    paid_at = db.Column(db.DateTime, nullable=True)

    merchant = db.relationship('User', foreign_keys=[merchant_id])
    payer = db.relationship('User', foreign_keys=[payer_id])

    def __repr__(self):
        return f"<Payment {self.payment_id} - {self.status}>"
