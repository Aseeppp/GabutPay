// PWA Service Worker Registration
window.addEventListener('load', () => {
  if ('serviceWorker' in navigator) {
    try {
      navigator.serviceWorker.register('/sw.js', { scope: '/' });
      console.log('Service Worker Registered');
    } catch (error) {
      console.error('Service Worker registration failed:', error);
    }
  }
});

// Initialize Animate on Scroll
AOS.init({
  duration: 600,
  once: true,
  offset: 50,
});

// --- Global Helper Functions ---

function showCopySuccess(button) {
    const originalButtonHTML = button.innerHTML;
    button.innerHTML = '<i class="bi bi-check-lg"></i> Tersalin!';
    button.disabled = true;
    button.classList.remove('btn-outline-secondary');
    button.classList.add('btn-success');
    
    setTimeout(function() {
        button.innerHTML = originalButtonHTML;
        button.disabled = false;
        button.classList.remove('btn-success');
        button.classList.add('btn-outline-secondary');
    }, 2000);
}

function copyToClipboard(button, elementId) {
    const copyText = document.getElementById(elementId);
    if (!copyText) return;

    copyText.select();
    copyText.setSelectionRange(0, 99999);

    if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(copyText.value).then(() => {
            showCopySuccess(button);
        }).catch(err => {
            console.error('Clipboard API failed, falling back.', err);
            if (document.execCommand('copy')) showCopySuccess(button);
        });
    } else {
        try {
            if (document.execCommand('copy')) showCopySuccess(button);
        } catch (e) {
            console.error('execCommand failed', e);
        }
    }
}

function onScanSuccess(decodedText, decodedResult) {
    const resultDiv = document.getElementById('qr-scan-result');
    console.log("--- QR SCAN SUCCESS ---");
    console.log("Raw decoded text:", decodedText);
    console.log("Decoded result object:", decodedResult);

    // Defensive check: Ensure we have a string to work with
    if (typeof decodedText !== 'string' || decodedText.trim() === '') {
        console.error("Scan result is not a valid string.");
        resultDiv.innerHTML = `<div class="alert alert-danger">Gagal membaca data QR. Hasil pindaian kosong atau tidak valid.</div>`;
        return;
    }

    // Stop scanning and show processing message
    try {
        if (window.html5QrcodeScanner && window.html5QrcodeScanner.getState() === 2) { // 2 is SCANNING state
            window.html5QrcodeScanner.clear();
            console.log("QR scanner cleared.");
        }
    } catch (e) {
        console.error("Error clearing scanner, continuing anyway.", e);
    }
    
    resultDiv.innerHTML = `
        <div class="spinner-border text-primary" role="status">
            <span class="visually-hidden">Loading...</span>
        </div>
        <p class="mt-2">Memproses QR Code...</p>
    `;

    // --- Main Processing Logic ---
    try {
        console.log("Attempting to parse JSON from decoded text...");
        const data = JSON.parse(decodedText);
        console.log("JSON parsed successfully:", data);

        const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
        console.log("CSRF Token found:", csrfToken ? 'Yes' : 'No');

        console.log("Sending fetch request to /verify-qr-payment...");
        fetch('/verify-qr-payment', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(data)
        })
        .then(response => {
            console.log("Received response from server. Status:", response.status);
            if (!response.ok) {
                console.error("Server responded with an error status.");
            }
            return response.json();
        })
        .then(result => {
            console.log("Parsed JSON response from server:", result);
            if (result.success && result.redirect_url) {
                console.log("Verification successful. Redirecting to:", result.redirect_url);
                window.location.href = result.redirect_url;
            } else {
                const errorMessage = String(result.error || 'Gagal memverifikasi QR code.');
                console.error("Verification failed. Server message:", errorMessage);
                resultDiv.innerHTML = `<div class="alert alert-danger">${errorMessage}</div>`;
            }
        })
        .catch(error => {
            const errorMessage = String(error);
            console.error('Fetch chain failed:', errorMessage);
            resultDiv.innerHTML = `<div class="alert alert-danger">Terjadi kesalahan saat menghubungi server: ${errorMessage}</div>`;
        });

    } catch (e) {
        const errorMessage = String(e);
        console.error("Top-level error in onScanSuccess (likely JSON.parse failed):", errorMessage);
        resultDiv.innerHTML = `<div class="alert alert-danger">QR Code tidak valid atau rusak. Pastikan gambar jelas dan hanya berisi QR code. Error: ${errorMessage}</div>`;
    }
}

function onScanFailure(error) {
    // This function is called frequently, so we don't log to avoid spam.
}


// --- Main DOMContentLoaded listener ---
document.addEventListener('DOMContentLoaded', () => {
    // Theme switcher logic
    const themeSwitcher = document.getElementById('theme-switcher');
    if (themeSwitcher) {
        const themeIcon = themeSwitcher.querySelector('i');
        
        // Function to update the icon based on the current theme
        const updateIcon = (theme) => {
            if (theme === 'dark') {
                themeIcon.classList.replace('bi-moon-stars-fill', 'bi-sun-fill');
            } else {
                themeIcon.classList.replace('bi-sun-fill', 'bi-moon-stars-fill');
            }
        };

        // Set the initial icon state based on the theme set by the inline script
        const initialTheme = document.documentElement.getAttribute('data-bs-theme');
        updateIcon(initialTheme);

        // Event listener for the switcher button
        themeSwitcher.addEventListener('click', () => {
            const newTheme = document.documentElement.getAttribute('data-bs-theme') === 'dark' ? 'light' : 'dark';
            localStorage.setItem('theme', newTheme);
            document.documentElement.setAttribute('data-bs-theme', newTheme);
            updateIcon(newTheme);
        });
    }

    // Push Notification Subscription Logic
    const subscribeCard = document.getElementById('subscribe-card');
    if (subscribeCard) {
        const subscribeButton = document.getElementById('subscribe-button');
        const vapidPublicKey = subscribeButton.dataset.vapidKey;

        function urlB64ToUint8Array(base64String) {
            const padding = '='.repeat((4 - base64String.length % 4) % 4);
            const base64 = (base64String + padding).replace(/\-/g, '+').replace(/_/g, '/');
            const rawData = window.atob(base64);
            const outputArray = new Uint8Array(rawData.length);
            for (let i = 0; i < rawData.length; ++i) {
                outputArray[i] = rawData.charCodeAt(i);
            }
            return outputArray;
        }

        function updateSubscriptionStatus(status, error = '') {
            if (status === 'subscribed') {
                subscribeCard.innerHTML = '<div class="card-body text-center"><p class="text-success mb-0"><i class="bi bi-check-circle-fill"></i> Anda sudah berlangganan notifikasi.</p></div>';
                subscribeCard.style.display = 'block';
            } else if (status === 'denied') {
                subscribeCard.innerHTML = '<div class="card-body text-center"><p class="text-warning mb-0"><i class="bi bi-exclamation-triangle-fill"></i> Anda memblokir notifikasi. Aktifkan manual di pengaturan browser.</p></div>';
                subscribeCard.style.display = 'block';
            } else if (status === 'unsubscribed') {
                subscribeCard.style.display = 'block';
                subscribeButton.disabled = false;
                subscribeButton.innerHTML = 'Aktifkan Notifikasi';
            } else if (status === 'error') {
                subscribeCard.innerHTML = `<div class="card-body text-center"><p class="text-danger mb-0">Gagal: ${error}</p></div>`;
                subscribeCard.style.display = 'block';
            }
        }

        if ('serviceWorker' in navigator && 'PushManager' in window) {
            navigator.serviceWorker.ready.then(reg => {
                if (Notification.permission === 'denied') {
                    updateSubscriptionStatus('denied');
                    return;
                }
                reg.pushManager.getSubscription().then(subscription => {
                    if (subscription) {
                        updateSubscriptionStatus('subscribed');
                    } else {
                        updateSubscriptionStatus('unsubscribed');
                    }
                });
            });

            subscribeButton.addEventListener('click', () => {
                subscribeButton.disabled = true;
                subscribeButton.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Memproses...';

                Notification.requestPermission().then(permission => {
                    if (permission !== 'granted') {
                        updateSubscriptionStatus('denied');
                        return;
                    }

                    navigator.serviceWorker.ready.then(reg => {
                        const applicationServerKey = urlB64ToUint8Array(vapidPublicKey);
                        reg.pushManager.subscribe({
                            userVisibleOnly: true,
                            applicationServerKey: applicationServerKey
                        }).then(subscription => {
                            console.log('User is subscribed:', subscription);
                            const csrfToken = document.querySelector('meta[name="csrf-token"]').getAttribute('content');
                            
                            fetch('/subscribe', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrfToken },
                                body: JSON.stringify(subscription)
                            }).then(res => {
                                if (res.ok) {
                                    updateSubscriptionStatus('subscribed');
                                } else {
                                    throw new Error('Gagal menyimpan langganan di server.');
                                }
                            }).catch(err => {
                                updateSubscriptionStatus('error', err.message);
                            });
                        }).catch(err => {
                            updateSubscriptionStatus('error', err.message);
                        });
                    });
                });
            });
        } else {
            updateSubscriptionStatus('error', 'Push Notification tidak didukung browser ini.');
        }
    }

    // Numeric input filter for PIN fields
    const numericInputs = document.querySelectorAll('input[inputmode="numeric"]');
    numericInputs.forEach(input => {
        input.addEventListener('input', () => {
            input.value = input.value.replace(/\D/g, '');
        });
    });

    // Copy to clipboard functionality
    const copyButtons = document.querySelectorAll('[data-copy-target]');
    copyButtons.forEach(button => {
        button.addEventListener('click', (e) => {
            const targetId = e.currentTarget.dataset.copyTarget;
            copyToClipboard(e.currentTarget, targetId);
        });
    });

    // Transfer page fee calculation
    const feeDetailsDiv = document.getElementById('fee-details');
    if (feeDetailsDiv) {
        const amountInput = document.getElementById('floatingAmount');
        const payerFeePercent = parseFloat(feeDetailsDiv.dataset.payerFeePercent);

        if(amountInput && !isNaN(payerFeePercent)) {
            amountInput.addEventListener('input', function() {
                const baseAmount = parseFloat(amountInput.value);
                
                if (isNaN(baseAmount) || baseAmount <= 0) {
                    feeDetailsDiv.innerHTML = '';
                    return;
                }

                const payerFee = baseAmount * payerFeePercent;
                const totalDebited = baseAmount + payerFee;

                const formatter = new Intl.NumberFormat('id-ID', {
                    style: 'currency',
                    currency: 'IDR',
                    minimumFractionDigits: 0,
                    maximumFractionDigits: 2
                });

                feeDetailsDiv.innerHTML = `
                    <span class="d-block">Biaya Layanan (Anda): <strong>${formatter.format(payerFee)}</strong></span>
                    <span class="d-block">Total yang akan dipotong: <strong>${formatter.format(totalDebited)}</strong></span>
                    <small class="d-block text-muted mt-1">Penerima akan mendapatkan bersih ${formatter.format(baseAmount)}.</small>
                `;
            });
        }
    }

    // QR Code Scanner Logic
    const qrReader = document.getElementById('qr-reader');
    if (qrReader) {
        console.log("QR Reader element found. Initializing scanner...");
        // The scanner UI with camera and gallery button
        window.html5QrcodeScanner = new Html5QrcodeScanner(
            "qr-reader",
            { 
                fps: 10, 
                qrbox: {width: 250, height: 250},
                experimentalFeatures: {
                    useBarCodeDetectorIfSupported: true
                }
            },
            /* verbose= */ false
        );
        window.html5QrcodeScanner.render(onScanSuccess, onScanFailure);
        console.log("html5QrcodeScanner.render() called.");

        // Workaround for buggy gallery scan: Manual file input
        const fileInput = document.getElementById('qr-file-input');
        fileInput.addEventListener('change', e => {
            if (e.target.files.length == 0) {
                return;
            }
            const imageFile = e.target.files[0];
            // Use the core engine directly, bypassing the UI scanner
            const html5QrCode = new Html5Qrcode( "qr-reader", /* verbose= */ false );
            html5QrCode.scanFile(imageFile, true)
            .then(decodedText => {
                // Manually call the same success function
                onScanSuccess(decodedText, { fileScan: true });
            })
            .catch(err => {
                // Manually call the same failure function
                onScanFailure(`File scan error: ${err}`);
            });
        });
    }
});
