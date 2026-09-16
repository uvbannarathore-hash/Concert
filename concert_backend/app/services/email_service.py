import os
import httpx
import logging
from app.config import SUPABASE_URL

logger = logging.getLogger(__name__)

def send_group_invite_email(invite_id: str, friend_email: str, initiator_name: str, event_name: str):
    """
    Attempts to send a group invite email by invoking the Supabase Edge Function synchronously.
    Throws an Exception on failure so the calling tool can report the error to the user.
    """
    webhook_secret = os.getenv("DB_WEBHOOK_SHARED_SECRET")
    if not webhook_secret or not SUPABASE_URL:
        logger.warning(f"[MOCK EMAIL] To: {friend_email}, Subject: {initiator_name} invited you to {event_name}! Link: /group-invite/{invite_id}")
        return

    try:
        with httpx.Client(timeout=10.0) as http_client:
            payload = {
                "type": "group_invite",
                "invite_id": invite_id,
                "friend_email": friend_email,
                "initiator_name": initiator_name,
                "event_name": event_name
            }
            resp = http_client.post(
                f"{SUPABASE_URL}/functions/v1/send-booking-notifications",
                json=payload,
                headers={"x-webhook-secret": webhook_secret, "Content-Type": "application/json"}
            )
            if resp.status_code != 200:
                err_msg = f"Failed to send email for invite {invite_id}: {resp.text}"
                logger.error(err_msg)
                raise Exception(err_msg)
            else:
                logger.info(f"Successfully triggered email for invite {invite_id}")
    except Exception as e:
        logger.error(f"Error calling edge function for email: {e}")
        raise e

def send_generic_notification(email: str | None, telegram_chat_id: str | None, subject: str, message: str):
    """
    Sends a generic notification via Supabase Edge Function to Email and/or Telegram.
    Synchronous and throws an Exception on failure.
    """
    webhook_secret = os.getenv("DB_WEBHOOK_SHARED_SECRET")
    if not webhook_secret or not SUPABASE_URL:
        logger.warning(f"[MOCK NOTIFICATION] To: {email}/{telegram_chat_id}, Subject: {subject}, Message: {message}")
        return

    try:
        with httpx.Client(timeout=10.0) as http_client:
            payload = {
                "type": "generic",
                "email": email,
                "telegram_chat_id": telegram_chat_id,
                "subject": subject,
                "message": message
            }
            resp = http_client.post(
                f"{SUPABASE_URL}/functions/v1/send-booking-notifications",
                json=payload,
                headers={"x-webhook-secret": webhook_secret, "Content-Type": "application/json"}
            )
            if resp.status_code != 200:
                err_msg = f"Failed to send generic notification: {resp.text}"
                logger.error(err_msg)
                raise Exception(err_msg)
            else:
                logger.info("Successfully triggered generic notification")
    except Exception as e:
        logger.error(f"Error calling edge function for generic notification: {e}")
        raise e

