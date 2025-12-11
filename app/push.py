import json
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_required, current_user
from pywebpush import webpush, WebPushException
from .models import PushSubscription, User
from . import db

push_bp = Blueprint('push', __name__)

def send_push_notification(user_id, payload):
    """
    Sends a push notification to a specific user.
    Handles deletion of expired/invalid subscriptions.
    Payload should be a dict, e.g., {"title": "Hello", "body": "..."}
    """
    try:
        user = User.query.get(user_id)
        if not user or not user.push_subscriptions:
            return

        vapid_claims = {
            "sub": f"mailto:{current_app.config['VAPID_CLAIM_EMAIL']}"
        }
        
        subscriptions_to_delete = []

        for sub in user.push_subscriptions:
            try:
                subscription_data = json.loads(sub.subscription_json)
                webpush(
                    subscription_info=subscription_data,
                    data=json.dumps(payload),
                    vapid_private_key=current_app.config['VAPID_PRIVATE_KEY'],
                    vapid_claims=vapid_claims
                )
            except WebPushException as ex:
                current_app.logger.warning(f"WebPushException for user {user_id}, sub ID {sub.id}: {ex}")
                # 404 and 410 status codes indicate the subscription is no longer valid.
                if ex.response and ex.response.status_code in [404, 410]:
                    current_app.logger.info(f"Marking subscription {sub.id} for deletion.")
                    subscriptions_to_delete.append(sub)
            except Exception as e:
                # Catch other potential errors like JSON parsing
                current_app.logger.error(f"Inner error sending push to sub {sub.id}: {e}")

        if subscriptions_to_delete:
            current_app.logger.info(f"Deleting {len(subscriptions_to_delete)} invalid subscriptions for user {user_id}.")
            for sub in subscriptions_to_delete:
                db.session.delete(sub)
            db.session.commit()

        current_app.logger.info(f"Finished sending push notifications to user {user_id}")

    except Exception as e:
        # Catch outer errors like failing to fetch the user
        db.session.rollback()
        current_app.logger.error(f"General error sending push notification to user {user_id}: {e}")


@push_bp.route('/subscribe', methods=['POST'])
@login_required
def subscribe():
    """
    Subscribes a user to push notifications.
    """
    subscription_data = request.get_json()
    if not subscription_data:
        return jsonify({'success': False, 'error': 'No subscription data provided.'}), 400

    # Check if this subscription already exists for this user
    endpoint = subscription_data.get('endpoint')
    existing_subscription = PushSubscription.query.filter(
        PushSubscription.user_id == current_user.id,
        PushSubscription.subscription_json.contains(endpoint)
    ).first()

    if existing_subscription:
        return jsonify({'success': True, 'message': 'Already subscribed.'})

    # Save the new subscription
    new_subscription = PushSubscription(
        user_id=current_user.id,
        subscription_json=json.dumps(subscription_data)
    )
    db.session.add(new_subscription)
    db.session.commit()

    return jsonify({'success': True, 'message': 'Subscription successful.'}), 201
