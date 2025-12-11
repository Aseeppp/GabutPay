from functools import wraps
from datetime import datetime, timedelta
from flask import Blueprint, render_template, flash, redirect, url_for, abort, request
from flask_login import login_required, current_user, logout_user
from . import db, bcrypt
from .models import User, Transaction
from decimal import Decimal
from .forms import ModifyBalanceForm, ManageBanForm, DeleteUserForm, WithdrawRevenueForm
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__)

# --- Decorator untuk memastikan hanya admin yang bisa akses ---
def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_admin:
            abort(403) # Forbidden
        return f(*args, **kwargs)
    return decorated_function

@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    user_count = User.query.count()
    total_balance = db.session.query(func.sum(User.balance)).scalar() or 0
    total_transactions = Transaction.query.count()
    recent_transactions = Transaction.query.order_by(Transaction.timestamp.desc()).limit(5).all()
    
    system_user = User.query.filter_by(email='sistem@gabutpay.com').first()
    system_revenue_balance = system_user.balance if system_user else 0
    
    return render_template(
        'admin_dashboard.html', 
        title='Admin Dashboard', 
        user_count=user_count,
        total_balance=total_balance,
        total_transactions=total_transactions,
        recent_transactions=recent_transactions,
        system_revenue_balance=system_revenue_balance
    )

@admin_bp.route('/users')
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    search_query = request.args.get('search', '')
    
    query = User.query
    if search_query:
        search_term = f"%{search_query}%"
        query = query.filter(
            db.or_(
                User.email.ilike(search_term),
                User.id.ilike(search_term)
            )
        )
        
    all_users = query.order_by(User.created_at.desc()).paginate(page=page, per_page=15)
    
    return render_template(
        'admin_users.html', 
        title='Kelola Pengguna', 
        users=all_users,
        now=datetime.utcnow
    )

@admin_bp.route('/user/<int:user_id>')
@admin_required
def edit_user(user_id):
    user = User.query.get_or_404(user_id)
    modify_balance_form = ModifyBalanceForm()
    manage_ban_form = ManageBanForm()
    delete_user_form = DeleteUserForm()
    return render_template(
        'admin_edit_user.html', 
        title=f'Edit Pengguna: {user.email}', 
        user=user,
        modify_balance_form=modify_balance_form,
        manage_ban_form=manage_ban_form,
        delete_user_form=delete_user_form,
        now=datetime.utcnow
    )

@admin_bp.route('/user/<int:user_id>/modify-balance', methods=['POST'])
@admin_required
def modify_balance(user_id):
    user = User.query.get_or_404(user_id)
    form = ModifyBalanceForm()
    if form.validate_on_submit():
        amount = Decimal(form.amount.data)
        amount_in_cents = int(amount * 100)
        reason = form.reason.data

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
    else:
        flash('Gagal mengubah saldo. Periksa kembali input Anda.', 'danger')
    return redirect(url_for('admin.edit_user', user_id=user_id))

@admin_bp.route('/user/<int:user_id>/manage-ban', methods=['POST'])
@admin_required
def manage_ban(user_id):
    user = User.query.get_or_404(user_id)
    form = ManageBanForm()
    if form.validate_on_submit():
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
                user.banned_until = datetime.utcnow() + timedelta(days=9999)
            flash(f'{user.email} telah diblokir.', 'warning')
        db.session.commit()
    else:
        flash('Aksi tidak valid.', 'danger')
    return redirect(url_for('admin.edit_user', user_id=user_id))

@admin_bp.route('/user/<int:user_id>/delete', methods=['POST'])
@admin_required
def delete_user(user_id):
    user_to_delete = User.query.get_or_404(user_id)
    form = DeleteUserForm()
    if form.validate_on_submit():
        if user_to_delete.id == current_user.id:
            flash('Anda tidak bisa menghapus akun Anda sendiri.', 'danger')
            return redirect(url_for('admin.edit_user', user_id=user_id))

        email = user_to_delete.email
        # Reassign transactions to a system/deleted user or handle otherwise
        Transaction.query.filter_by(user_id=user_to_delete.id).delete()
        db.session.delete(user_to_delete)
        db.session.commit()

        flash(f'Pengguna {email} dan semua datanya telah berhasil dihapus secara permanen.', 'success')
        return redirect(url_for('admin.users'))
    else:
        flash('Gagal menghapus pengguna.', 'danger')
        return redirect(url_for('admin.edit_user', user_id=user_id))

@admin_bp.route('/revenue')
@admin_required
def revenue():
    page = request.args.get('page', 1, type=int)
    system_user = User.query.filter_by(email='sistem@gabutpay.com').first()
    
    if not system_user:
        flash('Akun Kas Sistem tidak ditemukan. Harap restart aplikasi.', 'danger')
        return redirect(url_for('admin.dashboard'))

    transactions = Transaction.query.filter_by(user_id=system_user.id)\
        .order_by(Transaction.timestamp.desc())\
        .paginate(page=page, per_page=20)
    
    form = WithdrawRevenueForm()
    
    return render_template(
        'admin_revenue.html',
        title='Laporan Keuangan Sistem',
        system_user=system_user,
        transactions=transactions,
        form=form
    )

@admin_bp.route('/withdraw-revenue', methods=['POST'])
@admin_required
def withdraw_revenue():
    form = WithdrawRevenueForm()
    if form.validate_on_submit():
        amount_to_withdraw = int(Decimal(form.amount.data) * 100)
        pin = form.pin.data

        if not bcrypt.check_password_hash(current_user.pin_hash, pin):
            flash('PIN Keamanan Anda salah.', 'danger')
            return redirect(url_for('admin.revenue'))

        try:
            system_user = db.session.query(User).filter_by(email='sistem@gabutpay.com').with_for_update().one()
            admin_user = db.session.query(User).filter_by(id=current_user.id).with_for_update().one()

            if system_user.balance < amount_to_withdraw:
                flash('Saldo Akun Kas Sistem tidak mencukupi untuk penarikan ini.', 'danger')
                db.session.rollback()
                return redirect(url_for('admin.revenue'))

            # Perform the withdrawal
            system_user.balance -= amount_to_withdraw
            admin_user.balance += amount_to_withdraw

            # Create transaction records
            withdrawal_tx = Transaction(
                user_id=system_user.id,
                transaction_type='SYSTEM_WITHDRAWAL',
                amount=-amount_to_withdraw,
                description=f'Penarikan dana ke akun admin {admin_user.email}'
            )
            deposit_tx = Transaction(
                user_id=admin_user.id,
                transaction_type='ADMIN_DEPOSIT',
                amount=amount_to_withdraw,
                description='Deposit dana dari Akun Kas Sistem'
            )
            
            db.session.add_all([withdrawal_tx, deposit_tx])
            db.session.commit()
            flash(f'Berhasil menarik dana sebesar Rp {amount_to_withdraw/100:,.2f} dari Akun Kas Sistem.', 'success')

        except Exception as e:
            db.session.rollback()
            print(f"ERROR during revenue withdrawal: {e}")
            flash('Terjadi kesalahan internal saat penarikan dana.', 'danger')
    else:
        flash('Input tidak valid. Periksa kembali jumlah dan PIN Anda.', 'danger')

    return redirect(url_for('admin.revenue'))

