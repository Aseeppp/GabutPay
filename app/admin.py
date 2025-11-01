from functools import wraps
from datetime import datetime, timedelta
from flask import Blueprint, render_template, flash, redirect, url_for, abort, request
from flask_login import login_required, current_user, logout_user
from . import db
from .models import User, Transaction
from decimal import Decimal

admin_bp = Blueprint('admin', __name__)

# --- Decorator untuk memastikan hanya admin yang bisa akses ---
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            # Auto-ban logic
            ban_duration = timedelta(hours=1)
            current_user.banned_until = datetime.utcnow() + ban_duration
            db.session.commit()
            flash('Anda mencoba mengakses area terlarang. Akun Anda telah diblokir selama 1 jam.', 'danger')
            logout_user()
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    user_count = User.query.count()
    return render_template('admin_dashboard.html', title='Admin Dashboard', user_count=user_count)

@admin_bp.route('/users')
@admin_required
def users():
    all_users = User.query.order_by(User.created_at.desc()).all()
    return render_template('admin_users.html', title='Kelola Pengguna', users=all_users)

@admin_bp.route('/user/<int:user_id>')
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    return render_template('admin_edit_user.html', title=f'Edit Pengguna: {user.email}', user=user)

@admin_bp.route('/user/<int:user_id>/modify-balance', methods=['POST'])
@admin_required
def modify_balance(user_id):
    user = User.query.get_or_404(user_id)
    try:
        amount = Decimal(request.form.get('amount'))
        amount_in_cents = int(amount * 100)
    except:
        flash('Jumlah tidak valid.', 'danger')
        return redirect(url_for('admin.edit_user', user_id=user_id))
    
    reason = request.form.get('reason', 'Admin adjustment')

    user.balance += amount_in_cents
    
    tx_type = 'ADMIN_CREDIT' if amount_in_cents > 0 else 'ADMIN_DEBIT'

    adj_tx = Transaction(
        user_id=user.id,
        transaction_type=tx_type,
        amount=abs(amount_in_cents),
        description=f'Admin: {reason}'
    )
    db.session.add(adj_tx)
    db.session.commit()

    flash(f'Saldo untuk {user.email} berhasil diubah.', 'success')
    return redirect(url_for('admin.edit_user', user_id=user_id))

@admin_bp.route('/user/<int:user_id>/manage-ban', methods=['POST'])
@admin_required
def manage_ban(user_id):
    user = User.query.get_or_404(user_id)
    action = request.form.get('action')

    if action == 'unban':
        user.banned_until = None
        flash(f'Blokir untuk {user.email} telah dicabut.', 'success')
    elif action == 'ban':
        duration = request.form.get('duration')
        if duration == '1_hour':
            user.banned_until = datetime.utcnow() + timedelta(hours=1)
        elif duration == '1_day':
            user.banned_until = datetime.utcnow() + timedelta(days=1)
        elif duration == 'permanent':
            user.banned_until = datetime.utcnow() + timedelta(days=9999) # Far future date
        flash(f'{user.email} telah diblokir.', 'warning')

    db.session.commit()
    return redirect(url_for('admin.edit_user', user_id=user_id))

@admin_bp.route('/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    user_to_delete = User.query.get_or_404(user_id)

    if user_to_delete.id == current_user.id:
        flash('Anda tidak bisa menghapus akun Anda sendiri.', 'danger')
        return redirect(url_for('admin.edit_user', user_id=user_id))

    email = user_to_delete.email
    db.session.delete(user_to_delete)
    db.session.commit()

    flash(f'Pengguna {email} dan semua datanya telah berhasil dihapus secara permanen.', 'success')
    return redirect(url_for('admin.users'))

