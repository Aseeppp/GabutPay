import os
import requests
import uuid
from flask import Flask, render_template_string, request, redirect, url_for, jsonify, flash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'fu1soOach+kSv6h1ecMhKsF6z8ryuNHQN3UmZMvlWws='

# --- Konfigurasi Merchant ---
GABUTPAY_PUBLIC_KEY = "pk_test_6f2e1ae42f0c8f0a32d4eaf20f758cbe"
GABUTPAY_API_BASE_URL = "http://192.168.100.9:5001"

# --- Database Produk Fiktif ---
PRODUCTS = {
    'kaos-01': {"id": "kaos-01", "name": "Kaos Gabut Keren", "price": 7500000, "image_url": "https://via.placeholder.com/400x300.png?text=Kaos+Keren"},
    'mug-02': {"id": "mug-02", "name": "Mug Anti-Kerja", "price": 4500000, "image_url": "https://via.placeholder.com/400x300.png?text=Mug+Malas"},
    'stiker-03': {"id": "stiker-03", "name": "Stiker Laptop Rebahan", "price": 1500000, "image_url": "https://via.placeholder.com/400x300.png?text=Stiker+Rebahan"}
}

# --- Template HTML ---
HOME_TEMPLATE = '''
<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Toko Gabut</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet"></head><body>
<div class="container"><div class="text-center"><h1 class="display-4">Produk Paling Gabut</h1></div>
<div class="row row-cols-1 row-cols-md-3 g-4 mt-4">
    {% for product in products.values() %}
    <div class="col"><div class="card h-100"><img src="{{ product.image_url }}" class="card-img-top">
    <div class="card-body"><h5 class="card-title">{{ product.name }}</h5><p class="card-text fs-4 fw-bold">Rp {{ "{:,.2f}".format(product.price / 100) }}</p></div>
    <div class="card-footer"><form action="{{ url_for('create_payment', product_id=product.id) }}" method="POST"><div class="d-grid"><button type="submit" class="btn btn-primary">Beli Sekarang</button></div></form></div>
    </div></div>
    {% endfor %}
</div></div></body></html>
'''

PAYMENT_STATUS_TEMPLATE = '''
<!DOCTYPE html><html><head><title>Status Pembayaran</title><link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet"></head><body>
<div class="container text-center mt-5">
    {% if status == 'success' %}
        <h1 class="text-success">Pembayaran Berhasil!</h1>
        <p>Terima kasih sudah berbelanja. Pesanan Anda sedang diproses.</p>
    {% else %}
        <h1 class="text-danger">Pembayaran Gagal atau Dibatalkan.</h1>
        <p>Silakan coba lagi atau hubungi support.</p>
    {% endif %}
    <a href="/">Kembali ke Toko</a>
</div></body></html>
'''

# --- Rute Aplikasi ---
@app.route('/')
def home():
    return render_template_string(HOME_TEMPLATE, products=PRODUCTS)

@app.route('/bayar/<product_id>', methods=['POST'])
def create_payment(product_id):
    product = PRODUCTS.get(product_id)
    if not product:
        return "Produk tidak ditemukan", 404

    headers = {'X-PUBLIC-KEY': GABUTPAY_PUBLIC_KEY}
    payload = {
        "amount": product['price'],
        "merchant_order_id": f"INV-{uuid.uuid4().hex[:8]}",
        "description": product['name'],
        "redirect_url_success": url_for('payment_status', status='success', _external=True),
        "redirect_url_failure": url_for('payment_status', status='failure', _external=True)
    }
    
    try:
        api_url = f"{GABUTPAY_API_BASE_URL}/api/v1/create-payment"
        response = requests.post(api_url, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        payment_url = data.get('payment_url')
        return redirect(payment_url)
    except requests.exceptions.RequestException as e:
        return f"Gagal menghubungi layanan pembayaran: {e}", 500

@app.route('/payment-status/<status>')
def payment_status(status):
    return render_template_string(PAYMENT_STATUS_TEMPLATE, status=status)

@app.route('/webhook-gabutpay', methods=['POST'])
def gabutpay_webhook():
    payload = request.get_json()
    print("--- WEBHOOK DITERIMA ---")
    print(payload)
    print("------------------------")
    return jsonify({"status": "received"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5002, debug=True)
