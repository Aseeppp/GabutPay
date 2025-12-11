import random
from flask import Blueprint, render_template, request, jsonify, current_app
from flask_login import login_required, current_user
from . import db
from .models import User, Transaction

# --- Blueprint Definition ---
game_bp = Blueprint('game', __name__, template_folder='templates')

def init_games():
    """Placeholder function, not used for this game."""
    pass

# --- Game Constants ---
PRIZE_POOL = [
    # Common Prizes (75% chance)
    {'name': 'Zonk!', 'reward': 0, 'rarity': 'Biasa'},
    {'name': 'Hampir...', 'reward': 10000, 'rarity': 'Biasa'},
    {'name': 'Uang Receh', 'reward': 25000, 'rarity': 'Biasa'},
    
    # Uncommon Prizes (20% chance)
    {'name': 'Setengah Jalan', 'reward': 50000, 'rarity': 'Lumayan'},
    {'name': 'Modal Balik', 'reward': 100000, 'rarity': 'Lumayan'},

    # Rare Prize (4.5% chance)
    {'name': 'Untung Dikit', 'reward': 200000, 'rarity': 'Langka'},

    # Legendary Prize (0.5% chance)
    {'name': 'REJEKI ANAK SOLEH!', 'reward': 1000000, 'rarity': 'Legendaris'}
]
# Calculate weights for random.choices
PRIZE_WEIGHTS = {
    'Biasa': 75 / 3,
    'Lumayan': 20 / 2,
    'Langka': 4.5,
    'Legendaris': 0.5
}
weights = [PRIZE_WEIGHTS[p['rarity']] for p in PRIZE_POOL]


# --- Game Page Route ---
@game_bp.route('/play')
@login_required
def play():
    """Renders the Gacha game page."""
    return render_template('game.html', title='Gacha Gabut', gacha_cost=current_app.config['GACHA_COST'])

# --- Game API Route ---
@game_bp.route('/play-gacha', methods=['POST'])
@login_required
def play_gacha():
    """Endpoint to play the gacha."""
    user = current_user
    gacha_cost = current_app.config['GACHA_COST']

    if user.balance < gacha_cost:
        return jsonify({"error": f"Saldo tidak cukup. Anda memerlukan setidaknya Rp {gacha_cost/100}."}), 403

    try:
        # Use a transaction to ensure atomicity
        user_to_update = User.query.filter_by(id=user.id).with_for_update().one()

        # Deduct cost
        user_to_update.balance -= gacha_cost

        # Select prize based on weights
        chosen_prize = random.choices(PRIZE_POOL, weights=weights, k=1)[0]
        
        # Add reward
        user_to_update.balance += chosen_prize['reward']

        # Create transaction record
        tx_desc = f"Bermain Gacha: Mendapatkan '{chosen_prize['name']}'"
        # Net amount is reward - cost. Can be negative.
        net_amount = chosen_prize['reward'] - gacha_cost
        
        gacha_tx = Transaction(
            user_id=user.id, 
            transaction_type='GACHA_PLAY', 
            amount=net_amount, # Storing the net change
            description=tx_desc
        )
        db.session.add(gacha_tx)
        db.session.commit()

        return jsonify({
            "success": True,
            "prize": chosen_prize,
            "newBalance": user_to_update.balance
        })

    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error during gacha play: {e}")
        return jsonify({"error": "Terjadi kesalahan internal. Dana Anda aman."}), 500