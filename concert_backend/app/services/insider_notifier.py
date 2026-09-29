import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging
from app.supabase_client import supabase_admin

logger = logging.getLogger(__name__)

def trigger_insider_notifications(event_id: str):
    """
    Background task to notify matching subscribers about a newly approved event.
    Uses batching and a persistent SMTP connection for efficiency.
    """
    try:
        # 1. Fetch Event Details
        event_res = supabase_admin.table("events").select("event_id, artist_id, artist_name, city, venue_name, event_date, event_time").eq("event_id", event_id).execute()
        if not event_res.data:
            logger.error(f"Event {event_id} not found for notifications.")
            return
            
        event_data = event_res.data[0]
        artist_id = event_data.get("artist_id")
        city = event_data.get("city", "").strip().lower()
        artist_name = event_data.get("artist_name", "your favorite artist")
        
        # 2. Find matching subscribers who HAVEN'T been notified for this event
        # Logic: 
        # Match if: subscription is_active AND (subscription.city matches OR subscription.artist_id matches OR both are null)
        # AND NOT EXISTS in insider_notifications for this event_id
        
        # Since Supabase python client doesn't support complex NOT EXISTS easily in a single RPC without a custom function,
        # we'll fetch all active subscriptions, then fetch all sent notifications for this event, and filter in Python.
        # This is safe for 5-20 users, and scales decently up to a few thousand.
        
        subs_res = supabase_admin.table("insider_subscriptions").select("id, email, city, artist_id, unsubscribe_token").eq("is_active", True).execute()
        all_subs = subs_res.data or []
        
        notifs_res = supabase_admin.table("insider_notifications").select("subscription_id").eq("event_id", event_id).execute()
        notified_sub_ids = {n["subscription_id"] for n in (notifs_res.data or [])}
        
        # Filter matching
        matched_subs = []
        seen_emails = set()
        
        for sub in all_subs:
            if sub["id"] in notified_sub_ids:
                continue
                
            if sub["email"] in seen_emails:
                continue
                
            sub_city = sub.get("city")
            sub_artist = sub.get("artist_id")
            
            # Match condition:
            # 1. Global (both null)
            # 2. City match
            # 3. Artist match
            # A match happens if ANY of the criteria they set is met, or if they are global.
            match_city = (sub_city == city) if sub_city else False
            match_artist = (sub_artist == artist_id) if sub_artist else False
            is_global = (not sub_city and not sub_artist)
            
            if match_city or match_artist or is_global:
                matched_subs.append(sub)
                seen_emails.add(sub["email"])

        if not matched_subs:
            logger.info(f"No new subscribers to notify for event {event_id}.")
            return
            
        logger.info(f"Found {len(matched_subs)} subscribers to notify for event {event_id}.")
        
        # 3. Send Emails in Batch
        smtp_user = os.getenv("SMTP_USER", "dummy@example.com")
        smtp_pass = os.getenv("SMTP_PASS", "dummy")
        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", 587))
        
        frontend_url = os.getenv("VITE_PUBLIC_URL", "http://localhost:5173")
        event_url = f"{frontend_url}/concerts/{event_id}"
        
        subject = f"LiveWire Insider Alert: New Show in {event_data.get('city', 'Your City')}!"
        
        # Open persistent connection
        try:
            server = smtplib.SMTP(smtp_host, smtp_port)
            server.starttls()
            server.login(smtp_user, smtp_pass)
        except Exception as e:
            logger.error(f"Failed to connect to SMTP server: {e}")
            return
            
        success_count = 0
        for sub in matched_subs:
            try:
                msg = MIMEMultipart("alternative")
                msg["Subject"] = subject
                msg["From"] = f"LiveWire Insider <{smtp_user}>"
                msg["To"] = sub["email"]
                
                unsub_url = f"{frontend_url}/unsubscribe?token={sub['unsubscribe_token']}"
                
                html_body = f"""
                <html>
                  <body>
                    <h2>Hey! We have an exciting new show for you.</h2>
                    <p><strong>{artist_name}</strong> is performing at {event_data.get('venue_name')} on {event_data.get('event_date')} at {event_data.get('event_time')}.</p>
                    <p><a href="{event_url}">Click here to book your tickets now!</a></p>
                    <hr style="margin-top: 40px; border: none; border-top: 1px solid #eee;" />
                    <p style="font-size: 12px; color: #888;">
                      You are receiving this because you subscribed to LiveWire Insider alerts.
                      <br />
                      <a href="{unsub_url}" style="color: #888; text-decoration: underline;">Unsubscribe</a>
                    </p>
                  </body>
                </html>
                """
                msg.attach(MIMEText(html_body, "html"))
                
                # Send email
                server.sendmail(smtp_user, [sub["email"]], msg.as_string())
                
                # IMPORTANT: Only record as notified AFTER successful send
                supabase_admin.table("insider_notifications").insert({
                    "subscription_id": sub["id"],
                    "event_id": event_id
                }).execute()
                
                success_count += 1
                
            except Exception as e:
                logger.error(f"Failed to send/record notification for sub {sub['id']} ({sub['email']}): {e}")
                
        server.quit()
        logger.info(f"Finished Insider notifications for {event_id}. Successfully sent {success_count}/{len(matched_subs)}.")

    except Exception as e:
        logger.error(f"Error in trigger_insider_notifications for {event_id}: {e}")
