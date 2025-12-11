from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, BooleanField, TextAreaField, DecimalField, HiddenField, SelectField, FieldList
from wtforms.validators import DataRequired, Length, Email, EqualTo, ValidationError, Optional, NumberRange, Regexp, InputRequired

class RegistrationForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Konfirmasi Password', validators=[DataRequired(), EqualTo('password', message='Password harus cocok.')])
    submit = SubmitField('Daftar')

class LoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    remember = BooleanField('Ingat Saya')
    submit = SubmitField('Login')

class OTPForm(FlaskForm):
    otp = StringField('Kode OTP', validators=[DataRequired(), Length(min=6, max=6), Regexp(r'^\d{6}$', message='OTP harus 6 digit angka.')])
    submit = SubmitField('Verifikasi')

class ResetRequestForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    submit = SubmitField('Kirim Link Reset')

class ResetTokenForm(FlaskForm):
    password = PasswordField('Password Baru', validators=[DataRequired(), Length(min=8)])
    confirm_password = PasswordField('Konfirmasi Password Baru', validators=[DataRequired(), EqualTo('password', message='Password harus cocok.')])
    submit = SubmitField('Reset Password')

class SetPINForm(FlaskForm):
    pin = PasswordField('6-Digit PIN', validators=[DataRequired(), Length(min=6, max=6, message='PIN harus 6 digit.'), Regexp(r'^\d{6}$', message='PIN harus terdiri dari 6 digit angka.')])
    confirm_pin = PasswordField('Konfirmasi PIN', validators=[DataRequired(), EqualTo('pin', message='PIN harus cocok.'), Regexp(r'^\d{6}$', message='PIN harus terdiri dari 6 digit angka.')])
    next = HiddenField()
    submit = SubmitField('Atur PIN')

class ResetPINRequestForm(FlaskForm):
    submit = SubmitField('Kirim Link Reset PIN')

class ResetPINTokenForm(FlaskForm):
    pin = PasswordField('PIN Baru', validators=[DataRequired(), Length(min=6, max=6, message='PIN harus 6 digit.'), Regexp(r'^\d{6}$', message='PIN harus terdiri dari 6 digit angka.')])
    confirm_pin = PasswordField('Konfirmasi PIN Baru', validators=[DataRequired(), EqualTo('pin', message='PIN harus cocok.'), Regexp(r'^\d{6}$', message='PIN harus terdiri dari 6 digit angka.')])
    submit = SubmitField('Reset PIN')

class GenerateKeyForm(FlaskForm):
    store_name = StringField('Nama Toko', validators=[Optional()])
    pin = PasswordField('PIN Keamanan', validators=[DataRequired(), Length(min=6, max=6), Regexp(r'^\d{6}$', message='PIN harus terdiri dari 6 digit angka.')])
    submit = SubmitField('Konfirmasi & Buat Key')

class TransferForm(FlaskForm):
    recipient_email = StringField('Email Penerima', validators=[DataRequired(), Email()])
    amount = DecimalField('Jumlah', places=2, validators=[DataRequired(), NumberRange(min=0.01, message="Jumlah harus positif.")])
    pin = PasswordField('PIN Keamanan', validators=[DataRequired(), Length(min=6, max=6), Regexp(r'^\d{6}$', message='PIN harus terdiri dari 6 digit angka.')])
    submit = SubmitField('Transfer')

class PayPageForm(FlaskForm):
    pin = PasswordField('PIN Keamanan', validators=[DataRequired(), Length(min=6, max=6), Regexp(r'^\d{6}$', message='PIN harus terdiri dari 6 digit angka.')])
    submit = SubmitField('Konfirmasi & Bayar')

class BugReportForm(FlaskForm):
    subject = StringField('Subjek', validators=[DataRequired(), Length(min=5, max=100)])
    description = TextAreaField('Deskripsi Masalah', validators=[DataRequired(), Length(min=20)])
    submit = SubmitField('Kirim Laporan')

class EditKeyForm(FlaskForm):
    webhook_url = StringField('URL Webhook', validators=[Optional()])
    submit = SubmitField('Simpan Perubahan')

# Simple forms that only need a submit button and CSRF protection
class DeleteKeyForm(FlaskForm):
    key_id = HiddenField(validators=[DataRequired()])
    submit = SubmitField('Submit')

class ResetKeyForm(FlaskForm):
    key_id = HiddenField(validators=[DataRequired()])
    submit = SubmitField('Submit')

class ModifyBalanceForm(FlaskForm):
    amount = DecimalField('Jumlah', places=2, validators=[DataRequired()])
    reason = StringField('Alasan', validators=[DataRequired(), Length(min=5)])
    submit = SubmitField('Ubah Saldo')

class WithdrawRevenueForm(FlaskForm):
    amount = DecimalField('Jumlah Penarikan', places=2, validators=[DataRequired(), NumberRange(min=100, message="Jumlah minimal Rp 100.")])
    pin = PasswordField('PIN Keamanan Anda', validators=[DataRequired(), Length(min=6, max=6), Regexp(r'^\d{6}$', message='PIN harus terdiri dari 6 digit angka.')])
    submit = SubmitField('Tarik Dana')

class ManageBanForm(FlaskForm):
    action = HiddenField(validators=[DataRequired()])
    duration = StringField('Durasi', validators=[Optional()]) # Only used for 'ban' action
    submit = SubmitField('Submit') # Button text will be set in template

class DeleteUserForm(FlaskForm):
    submit = SubmitField('Delete')

class RequestQRForm(FlaskForm):
    amount = DecimalField('Jumlah', places=2, validators=[DataRequired(), NumberRange(min=1, message="Jumlah harus lebih dari 0.")])
    submit = SubmitField('Buat QR Code')

class SplitBillForm(FlaskForm):
    title = StringField('Judul Tagihan', validators=[DataRequired(), Length(min=3, max=100)])
    description = TextAreaField('Deskripsi (Opsional)', validators=[Optional(), Length(max=500)])
    total_amount = DecimalField('Total Tagihan', places=2, validators=[DataRequired(), NumberRange(min=1, message="Jumlah harus lebih dari 0.")])
    participants = FieldList(StringField('Email Peserta', validators=[InputRequired(message="Email tidak boleh kosong."), Email(message="Email tidak valid.")]), min_entries=1)
    submit = SubmitField('Lanjut ke Konfirmasi')
