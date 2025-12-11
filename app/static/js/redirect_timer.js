document.addEventListener('DOMContentLoaded', function() {
    const targetLink = document.getElementById('target-link');
    if (!targetLink) return;

    const targetUrl = targetLink.href;
    let countdownElement = document.getElementById('countdown');
    let seconds = 5;

    const interval = setInterval(() => {
        seconds--;
        if (countdownElement) {
            countdownElement.textContent = `Mengarahkan dalam ${seconds} detik...`;
        }
        if (seconds <= 0) {
            clearInterval(interval);
            window.location.href = targetUrl;
        }
    }, 1000);
});
