import os
import sys
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("retry_group_emails")

# Add the project root to sys.path before importing app modules
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.supabase_client import supabase_admin
from app.services.email_service import send_group_invite_email

def retry_emails():
    """
    Retries group invite emails that failed or are pending.
    Limits to 3 attempts total.
    """
    logger.info("Starting group invite email retry job...")

    try:
        # Fetch pending and failed invites (less than 3 attempts)
        invites_res = supabase_admin.table("group_booking_invites") \
            .select("*, group_booking_sessions(*)") \
            .in_("email_status", ["pending", "failed"]) \
            .lt("email_attempts", 3) \
            .execute()
            
        invites = invites_res.data
        if not invites:
            logger.info("No emails to retry.")
            return

        success_count = 0
        fail_count = 0

        for invite in invites:
            session = invite.get("group_booking_sessions")
            if not session or session.get("status") != "collecting_responses":
                continue # Skip if session is expired or cancelled or booked

            invite_id = invite["id"]
            em = invite["friend_email"]
            attempts = invite.get("email_attempts", 0)

            # Get event name
            event_res = supabase_admin.table("events").select("event_name:artist_name").eq("event_id", session["event_id"]).execute()
            event_name = event_res.data[0].get("event_name", "a concert") if event_res.data else "a concert"

            # Get initiator name
            user_res = supabase_admin.table("users").select("name").eq("user_id", session["initiator_user_id"]).execute()
            initiator_name = user_res.data[0].get("name", "A friend") if user_res.data else "A friend"

            logger.info(f"Retrying email for invite {invite_id} ({em}) - attempt {attempts + 1}")

            try:
                send_group_invite_email(invite_id, em, initiator_name, event_name)
                # Success
                supabase_admin.table("group_booking_invites").update({
                    "email_status": "sent",
                    "email_attempts": attempts + 1,
                    "last_email_attempt_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", invite_id).execute()
                success_count += 1
                logger.info(f"Successfully sent email to {em}")
            except Exception as e:
                # Failure
                logger.warning(f"Failed to send email to {em}: {e}")
                supabase_admin.table("group_booking_invites").update({
                    "email_status": "failed",
                    "email_error": str(e),
                    "email_attempts": attempts + 1,
                    "last_email_attempt_at": datetime.now(timezone.utc).isoformat()
                }).eq("id", invite_id).execute()
                fail_count += 1

        logger.info(f"Retry job completed. Success: {success_count}, Failed: {fail_count}")

    except Exception as e:
        logger.error(f"Error in retry job: {e}")

if __name__ == "__main__":
    retry_emails()
