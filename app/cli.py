import click
from flask.cli import with_appcontext
from . import db, bcrypt
from .models import User, Achievement
import secrets

@click.command('seed-data')
@with_appcontext
def seed_data_command():
    """Membuat data awal yang diperlukan oleh aplikasi, seperti akun sistem."""
    
    # --- Buat Akun Kas Sistem ---
    if User.query.filter_by(email='sistem@gabutpay.com').first():
        click.echo('Akun Kas Sistem sudah ada.')
    else:
        system_user = User(
            email='sistem@gabutpay.com',
            password_hash=bcrypt.generate_password_hash(secrets.token_hex(32)).decode('utf-8'),
            is_verified=True,
            is_admin=False # Ini bukan admin yang bisa login
        )
        db.session.add(system_user)
        click.echo('Membuat Akun Kas Sistem...')
    
    # Commit perubahan ke database
    db.session.commit()
    click.echo('Seeding data selesai.')

@click.command('seed-achievements')
@with_appcontext
def seed_achievements_command():
    """Mengisi database dengan daftar achievements awal."""
    
    achievements = [
        {'code': 'FIRST_TRANSFER', 'name': 'Pengirim Perdana', 'description': 'Berhasil melakukan transfer pertama kali.', 'icon': 'bi-send-check-fill'},
        {'code': 'TRANSFER_5', 'name': 'Kurir Handal', 'description': 'Melakukan 5 kali transfer.', 'icon': 'bi-send-exclamation-fill'},
        {'code': 'FIRST_PAYMENT_IN', 'name': 'Juragan Awal', 'description': 'Menerima pembayaran pertama dari orang lain.', 'icon': 'bi-piggy-bank-fill'},
        {'code': 'GACHA_ADDICT_10', 'name': 'Mulai Kecanduan', 'description': 'Bermain Gacha sebanyak 10 kali.', 'icon': 'bi-dice-5-fill'},
        {'code': 'STREAK_7', 'name': 'Rajin Pangkal Pandai', 'description': 'Login 7 hari berturut-turut.', 'icon': 'bi-calendar-heart-fill'},
    ]
    
    click.echo('Memulai seeding achievements...')
    for ach_data in achievements:
        ach = Achievement.query.filter_by(code=ach_data['code']).first()
        if ach:
            click.echo(f"Achievement '{ach_data['name']}' sudah ada, dilewati.")
        else:
            new_ach = Achievement(**ach_data)
            db.session.add(new_ach)
            click.echo(f"Membuat achievement: '{ach_data['name']}'")
            
    db.session.commit()
    click.echo('Seeding achievements selesai.')


def init_cli(app):
    """Mendaftarkan perintah CLI."""
    app.cli.add_command(seed_data_command)
    app.cli.add_command(seed_achievements_command)
