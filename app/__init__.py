
from flask import Flask, request, g, flash, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, current_user, logout_user
from flask_bcrypt import Bcrypt
from flask_mail import Mail
from flask_talisman import Talisman
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from dotenv import load_dotenv
from flask_migrate import Migrate
import os
from datetime import datetime

# Load environment variables
load_dotenv()

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()
mail = Mail()
csrf = CSRFProtect()
migrate = Migrate()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day"],
    storage_uri="memory://"
)

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
    app.config['QR_HMAC_SECRET_KEY'] = os.environ.get('QR_HMAC_SECRET_KEY')
    
    # Database configuration: Prefer DATABASE_URL if available (e.g., on Heroku),
    # otherwise, fall back to a local SQLite database.
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url or 'sqlite:///site.db'
    
    # Business logic configurations
    app.config['KEY_COST'] = int(os.environ.get('KEY_COST', 1000000))
    app.config['GACHA_COST'] = int(os.environ.get('GACHA_COST', 100000))
    app.config['REGISTRATION_BONUS'] = int(os.environ.get('REGISTRATION_BONUS', 100000)) # Rp 1,000.00
    app.config['DAILY_LOGIN_BONUS'] = int(os.environ.get('DAILY_LOGIN_BONUS', 5000)) # Rp 50.00
    
    
    # New Fee Structure
    app.config['MERCHANT_FEE_PERCENT'] = float(os.environ.get('MERCHANT_FEE_PERCENT', 0.10)) # 10%
    app.config['PAYER_FEE_LINK_PERCENT'] = float(os.environ.get('PAYER_FEE_LINK_PERCENT', 0.10)) # 10%
    app.config['PAYER_FEE_QR_PERCENT'] = float(os.environ.get('PAYER_FEE_QR_PERCENT', 0.07)) # 7%
    app.config['PAYER_FEE_TRANSFER_PERCENT'] = float(os.environ.get('PAYER_FEE_TRANSFER_PERCENT', 0.07)) # 7%
    
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['ADMIN_EMAIL'] = os.environ.get('ADMIN_EMAIL')

    # VAPID keys for push notifications
    app.config['VAPID_PUBLIC_KEY'] = os.environ.get('VAPID_PUBLIC_KEY')
    app.config['VAPID_PRIVATE_KEY'] = os.environ.get('VAPID_PRIVATE_KEY')
    app.config['VAPID_CLAIM_EMAIL'] = os.environ.get('ADMIN_EMAIL') # Use admin email for claim

    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    mail.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    migrate.init_app(app, db)

    # Content Security Policy
    csp = {
        'default-src': [
            '\'self\'',
            'https://cdn.jsdelivr.net',
            'https://unpkg.com' # Needed for AOS
        ],
        'script-src': [
            '\'self\'',
            'https://cdn.jsdelivr.net',
            'https://unpkg.com', # Needed for AOS
            '\'sha256-WE9cek3jMYEHymorbohXeZBLX/ZYX9M8DsphH4pW764=\'' # Hash for inline theme-setter script
        ],
        'style-src': [
            '\'self\'',
            'https://cdn.jsdelivr.net',
            'https://fonts.googleapis.com', # Needed for Google Fonts
            'https://unpkg.com', # Needed for AOS
            '\'unsafe-hashes\'', # Allow hashes for inline style attributes (needed for AOS)
            '\'sha256-83Z7BrTq1JySMUhKdpxG8Gh16A8kQogdPXmAwDEw5w8=\'', # AOS injected style
            '\'sha256-xVEK7gcaeJAqZHgUjP0ktYmyVcW5brxPqD47mQeu5uw=\'', # AOS injected style
            '\'sha256-nhgk42D0M3yhhKg308rg1MML5GAh6pVlmOHDdS+M+xM=\'', # AOS injected style
            '\'sha256-50qoRtsVj3+R3qmroal3gUTURgclxnqvRaNJ5PfyFGY=\'',  # AOS injected style
            '\'sha256-H4JZobrI8+QfMKI75330WH/CaWduQbOpkwbmRqjDZxQ=\'',   # AOS injected style
            '\'sha256-JlJlQ5PCBCWS8Ykr0MavXrS+CnlqoIed14HOPqHUgXs=\'',  # AOS injected style
            '\'sha256-biLFinpqYMtWHmXfkA1BPeCY0/fNt46SAZ+BBk5YUog=\''   # Bootstrap modal style
        ],
        'font-src': [
            '\'self\'',
            'https://fonts.gstatic.com' # Needed for Google Fonts
        ],
        'img-src': [
            '\'self\'',
            'data:', # Needed for Bootstrap SVGs
            'blob:' # Needed for html5-qrcode camera feed
        ]
    }
    Talisman(
        app, 
        content_security_policy=csp,
        permissions_policy={'clipboard-write': '*'}
    )

    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'info'

    @app.before_request
    def check_banned_user():
        if current_user.is_authenticated and current_user.banned_until:
            if datetime.utcnow() < current_user.banned_until:
                logout_user()
                flash('Akun Anda telah diblokir. Silakan hubungi support untuk informasi lebih lanjut.', 'danger')
                return redirect(url_for('auth.login'))

    from .routes import main_bp
    app.register_blueprint(main_bp)

    from .auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from .api import api_bp
    csrf.exempt(api_bp)
    app.register_blueprint(api_bp, url_prefix='/api/v1')

    from .admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from .game import game_bp, init_games
    csrf.exempt(game_bp)
    app.register_blueprint(game_bp, url_prefix='/game')

    from .qr_payment import qr_payment_bp
    csrf.exempt(qr_payment_bp)
    app.register_blueprint(qr_payment_bp)

    from .cli import init_cli
    init_cli(app)

    from .push import push_bp
    csrf.exempt(push_bp)
    app.register_blueprint(push_bp)

    return app
