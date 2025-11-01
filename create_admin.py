import sys
import getpass
from run import app
from app import db, bcrypt
from app.models import User

def create_admin():
    """Fungsi untuk membuat user admin baru secara interaktif."""
    with app.app_context():
        print("--- Pembuatan Akun Admin Baru GabutPay ---")
        
        # 1. Meminta dan memvalidasi Email
        email = input("Masukkan Email untuk admin baru: ").strip()
        if not email:
            print("\nERROR: Email tidak boleh kosong.")
            return
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            print(f"\nERROR: User dengan email {email} sudah ada.")
            return

        # 2. Meminta dan memvalidasi Password
        password = getpass.getpass("Masukkan Password (minimal 8 karakter): ").strip()
        if len(password) < 8:
            print("\nERROR: Password minimal harus 8 karakter.")
            return
            
        confirm_password = getpass.getpass("Konfirmasi Password: ").strip()
        if password != confirm_password:
            print("\nERROR: Password tidak cocok.")
            return

        # 3. Membuat user admin baru
        try:
            hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
            new_admin = User(
                email=email,
                password_hash=hashed_password,
                is_admin=True,
                is_verified=True # Admin yang dibuat via CLI langsung terverifikasi
            )
            db.session.add(new_admin)
            db.session.commit()
            print(f"\nSUKSES: Akun admin untuk {email} telah berhasil dibuat.")
        except Exception as e:
            db.session.rollback()
            print(f"\nERROR: Terjadi kesalahan saat menyimpan ke database: {e}")

if __name__ == "__main__":
    create_admin()