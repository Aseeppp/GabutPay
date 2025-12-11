document.addEventListener('DOMContentLoaded', function () {
    // --- DOM Elements ---
    const chestArea = document.getElementById('chest-area');
    const chestLid = document.getElementById('chest-lid');
    const playButton = document.getElementById('play-gacha-btn');
    const resultCard = document.getElementById('prize-card');
    const cardBack = resultCard.querySelector('.card-back');
    const prizeRarityEl = document.getElementById('prize-rarity');
    const prizeNameEl = document.getElementById('prize-name');
    const prizeRewardEl = document.getElementById('prize-reward');
    const balanceElement = document.getElementById('navbar-balance');
    const actionButtonContainer = document.getElementById('action-button');
    const celebrationContainer = document.getElementById('celebration-container');
    const gachaContainer = document.querySelector('.gacha-container');
    const playUrl = gachaContainer.dataset.playUrl;

    // --- Utility ---
    const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

    // --- State ---
    let isPlaying = false;

    // --- Main Game Logic ---
    const playGacha = async () => {
        if (isPlaying) return;
        isPlaying = true;

        await resetToInitialState();
        setDisabled(true);
        
        // 1. Shaking
        chestArea.classList.add('chest-shaking');
        playButton.textContent = 'Mengocok...';
        await sleep(2000);
        
        // 2. Fetching result
        chestArea.classList.remove('chest-shaking');
        playButton.textContent = 'Membuka...';

        try {
            const response = await fetch(playUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                }
            });

            const contentType = response.headers.get("content-type");
            if (contentType && contentType.indexOf("application/json") !== -1) {
                const data = await response.json();
                if (!response.ok) {
                    throw new Error(data.error || 'Terjadi kesalahan server.');
                }
                await revealPrize(data);
            } else {
                showError("Sesi kamu habis. Halaman akan dimuat ulang...");
                await sleep(2000);
                window.location.reload();
                return;
            }

        } catch (error) {
            showError(error.message);
        } finally {
            actionButtonContainer.innerHTML = `<button id="play-again-btn" class="btn btn-secondary btn-lg">Main Lagi</button>`;
            document.getElementById('play-again-btn').addEventListener('click', playGacha);
            isPlaying = false;
        }
    };

    const revealPrize = async (data) => {
        const { prize, newBalance } = data;

        // 3. Show rarity aura
        if (prize.rarity !== 'Biasa') {
            chestArea.classList.add(`aura-${prize.rarity}`);
        }
        await sleep(1500);

        // 4. Open lid
        chestLid.classList.add('lid-opening');
        await sleep(500);

        // 5. Card flies in
        populateCard(prize);
        resultCard.classList.add('visible');
        await sleep(800);

        // 6. Flip the card
        resultCard.classList.add('flipped');
        
        // 7. Celebration
        triggerCelebration(prize.rarity);

        // Hide the main button
        playButton.style.display = 'none';

        // Update balance in navbar
        if (balanceElement) {
            const formattedBalance = (newBalance / 100).toLocaleString('id-ID');
            balanceElement.textContent = `Rp ${formattedBalance}`;
        }
    };

    // --- Helper Functions ---
    const setDisabled = (disabled) => {
        playButton.disabled = disabled;
        chestArea.classList.toggle('disabled', disabled);
    };

    const resetToInitialState = async () => {
        resultCard.classList.remove('visible', 'flipped');
        await sleep(300); // allow card to fade out before resetting content
        chestLid.classList.remove('lid-opening');
        chestArea.className = ''; // remove all aura classes
        celebrationContainer.innerHTML = '';
        cardBack.className = 'card-face card-back';
        playButton.style.display = 'block';
        actionButtonContainer.innerHTML = '';
        actionButtonContainer.appendChild(playButton);
        playButton.textContent = `Buka Peti (Rp 100)`;
        setDisabled(false);
    };

    const populateCard = (prize) => {
        const rewardInRupiah = prize.reward / 100;
        const rewardText = prize.reward > 0 ? `Dapat Rp ${rewardInRupiah.toLocaleString('id-ID')}!` : 'Zonk! Coba lagi ya!';
        
        prizeRarityEl.textContent = prize.rarity;
        prizeNameEl.textContent = prize.name;
        prizeRewardEl.textContent = rewardText;
        cardBack.classList.add(`rarity-${prize.rarity}`);
    };

    const triggerCelebration = (rarity) => {
        if (rarity === 'Biasa') return;

        let particleCount = 0;
        if (rarity === 'Langka') particleCount = 50;
        if (rarity === 'Legendaris') particleCount = 150;
        if (rarity === 'Lumayan') particleCount = 20;

        for (let i = 0; i < particleCount; i++) {
            const confetti = document.createElement('div');
            confetti.className = 'confetti';
            confetti.style.left = `${Math.random() * 100}vw`;
            confetti.style.animationDelay = `${Math.random() * 2}s`;
            
            const hue = (rarity === 'Legendaris' || rarity === 'Langka') ? '40' : '200';
            confetti.style.backgroundColor = `hsl(${hue}, 90%, ${Math.random() * 50 + 50}%)`;
            
            celebrationContainer.appendChild(confetti);
        }
    };

    const showError = (message) => {
        prizeRarityEl.textContent = 'Error';
        prizeNameEl.textContent = message;
        prizeRewardEl.textContent = 'Dana kamu aman, coba lagi nanti.';
        cardBack.classList.add('rarity-Biasa');
        
        resultCard.classList.add('visible', 'flipped');
        playButton.style.display = 'none';
    };

    const getCsrfToken = () => {
        const token = document.querySelector('meta[name="csrf-token"]');
        if (token) return token.getAttribute('content');
        console.error('CSRF token not found');
        return '';
    };

    // --- Event Listeners ---
    playButton.addEventListener('click', playGacha);
    chestArea.addEventListener('click', () => {
        if (!isPlaying) playButton.click();
    });
});