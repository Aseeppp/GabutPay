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
    last_seen = db.Column(db.DateTime, nullable=True)
    login_streak = db.Column(db.Integer, nullable=False, server_default='0', default=0)
    
    # Relationship to APIKey
    api_keys = db.relationship('APIKey', backref='owner', lazy=True, cascade="all, delete-orphan")
    push_subscriptions = db.relationship('PushSubscription', backref='user', lazy=True, cascade="all, delete-orphan")
    achievements = db.relationship('UserAchievement', backref='user', lazy=True, cascade="all, delete-orphan")

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
    secret_key_encrypted = db.Column(db.String(512), nullable=True) # Stores the encrypted secret key
    webhook_secret_hash = db.Column(db.String(128), nullable=False)
    # This field will store the encrypted webhook secret.
    webhook_secret_encrypted = db.Column(db.String(512), nullable=True)
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
    payment_id = db.Column(db.Integer, db.ForeignKey('payment.id'), nullable=True) # Link to the payment
    transaction_type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    counterparty_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    description = db.Column(db.String(255), nullable=True)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref=db.backref('transactions', cascade="all, delete-orphan"))
    counterparty = db.relationship('User', foreign_keys=[counterparty_id])
    payment = db.relationship('Payment', backref=db.backref('transactions', cascade="all, delete-orphan"))

    def __repr__(self):
        return f"Transaction('{self.user.email}', '{self.transaction_type}', {self.amount})"

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    payment_id = db.Column(db.String(36), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))
    
    merchant_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    payer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    
    amount = db.Column(db.Integer, nullable=False) # Base amount in cents
    payer_fee = db.Column(db.Integer, nullable=False, default=0)
    merchant_fee = db.Column(db.Integer, nullable=False, default=0)

    payment_method = db.Column(db.String(20), nullable=True) # e.g., 'LINK', 'QR', 'TRANSFER'
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

    def get_signed_id(self, expires_sec=600):
        s = URLSafeTimedSerializer(current_app.config['SECRET_KEY'])
        return s.dumps(self.payment_id, salt='payment-url-salt')

class PushSubscription(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subscription_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def __repr__(self):
        return f"<PushSubscription {self.user.email}>"

class SplitBill(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    total_amount = db.Column(db.Integer, nullable=False)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='ACTIVE') # ACTIVE, COMPLETED, CANCELLED
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    creator = db.relationship('User', backref=db.backref('created_split_bills', lazy=True))
    participants = db.relationship('SplitBillParticipant', backref='split_bill', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SplitBill {self.id}: '{self.title}'>"

class SplitBillParticipant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    split_bill_id = db.Column(db.Integer, db.ForeignKey('split_bill.id'), nullable=False)
    participant_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    participant_email = db.Column(db.String(120), nullable=False, index=True)
    amount_due = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default='PENDING') # PENDING, PAID
    payment_id = db.Column(db.Integer, db.ForeignKey('payment.id'), nullable=True)

    user = db.relationship('User', backref=db.backref('split_bill_participations', lazy=True))
    payment = db.relationship('Payment', backref=db.backref('split_bill_source', lazy='select'))

    def __repr__(self):
        return f"<SplitBillParticipant {self.id} for SplitBill {self.split_bill_id}>"

class Achievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False) # e.g., 'TRANSFER_5', 'FIRST_PAYMENT'
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.String(255), nullable=False)
    icon = db.Column(db.String(50), nullable=False, default='bi-star-fill') # Bootstrap icon class

    def __repr__(self):
        return f"<Achievement {self.name}>"

class UserAchievement(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    achievement_id = db.Column(db.Integer, db.ForeignKey('achievement.id'), nullable=False)
    unlocked_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint('user_id', 'achievement_id', name='_user_achievement_uc'),)

    achievement = db.relationship('Achievement', backref='unlocks')

    def __repr__(self):
        return f"<UserAchievement user:{self.user_id} achievement:{self.achievement_id}>"


