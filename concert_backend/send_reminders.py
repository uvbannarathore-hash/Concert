import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os
import httpx
from google import genai

load_dotenv()

from app.supabase_client import supabase_admin
from app.config import GEMINI_API_KEY
from app.services.ai_service import generate_content_with_fallback

async def main():
    print("Running AI Proactive Reminder Agent...")
    
    # Calculate the 24-hour target window (23h to 25h from now)
    now = datetime.now(timezone.utc)
    target_start = now + timedelta(hours=23)
    target_end = now + timedelta(hours=25)
    
    supabase_url = os.getenv("SUPABASE_URL")
    webhook_secret = os.getenv("DB_WEBHOOK_SHARED_SECRET")
    
    if not GEMINI_API_KEY:
        print("GEMINI_API_KEY is missing.")
        return

    try:
        # Fetch upcoming events in date range to narrow down
        date_start_str = target_start.strftime("%Y-%m-%d")
        date_end_str = (target_end + timedelta(days=1)).strftime("%Y-%m-%d")
        
        events_res = supabase_admin.table("events").select("*").gte("event_date", date_start_str).lte("event_date", date_end_str).execute()
        
        if not events_res.data:
            print("No events found in date range.")
            return

        eligible_events = []
        for evt in events_res.data:
            try:
                # Parse event datetime. Explicitly assuming Asia/Kolkata (IST) for event data.
                # The DB stores event_time in 24-hour HH:MM format (e.g. "10:00", "19:00").
                # Fall back to 12-hour "%I:%M %p" in case a legacy value like "07:00 PM" is returned.
                dt_str = f"{evt['event_date']} {evt['event_time']}"
                for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p"):
                    try:
                        evt_dt_naive = datetime.strptime(dt_str, fmt)
                        break
                    except ValueError:
                        continue
                else:
                    raise ValueError(f"Unrecognised event_time format: {evt['event_time']!r}")
                ist_tz = timezone(timedelta(hours=5, minutes=30))
                evt_dt = evt_dt_naive.replace(tzinfo=ist_tz)
                
                # target_start and target_end are UTC, so datetime comparison handles the offset correctly
                if target_start <= evt_dt <= target_end:
                    eligible_events.append(evt)
            except Exception as e:
                print(f"Skipping event {evt.get('event_id')} due to datetime parse error: {e}")

        if not eligible_events:
            print("No events exactly in the 24-hour window.")
            return

        for evt in eligible_events:
            event_id = evt["event_id"]
            
            prompt = f"""
            You are the LiveWire Proactive Reminder Agent. Generate a short, exciting prep guide for the upcoming event:
            Artist: {evt.get('artist_name')}
            Venue: {evt.get('venue_name')}, {evt.get('city')}
            Date: {evt.get('event_date')} at {evt.get('event_time')}
            
            CRITICAL RULE: You are NOT allowed to invent or hallucinate ANY specific gate numbers, travel conditions, parking details, venue rules, opening times, or setlists. You must ONLY use the factual data provided above. Because specific factual information (like gate numbers or setlists) is not provided in this prompt, you MUST either explicitly state that the information is unavailable, or provide ONLY general exciting preparation advice. Keep it under 2 short paragraphs.
            """
            
            response = generate_content_with_fallback(
                model='gemini-3.6-flash',
                contents=prompt,
            )
            ai_text = response.text.strip()
            
            print(f"Generated AI reminder for {event_id}:\n{ai_text}\n")
            
            # Find eligible confirmed bookings. We use the specific channel flags because 
            # the legacy pg_cron might have already set reminder_sent = True silently.
            bookings_res = supabase_admin.table("bookings").select("booking_id") \
                .eq("event_id", event_id) \
                .eq("status", "Confirmed") \
                .eq("payment_status", "Paid") \
                .or_("reminder_email_sent.eq.false,reminder_telegram_sent.eq.false") \
                .execute()
            
            if not bookings_res.data:
                print(f"No unreminded confirmed bookings for {event_id}.")
                continue
                
            # Hit edge function explicitly for each eligible booking
            async with httpx.AsyncClient() as http_client:
                for b in bookings_res.data:
                    payload = {
                        "type": "event_reminder",
                        "booking_id": b["booking_id"],
                        "ai_content": ai_text
                    }
                    resp = await http_client.post(
                        f"{supabase_url}/functions/v1/send-booking-notifications",
                        json=payload,
                        headers={"x-webhook-secret": webhook_secret, "Content-Type": "application/json"}
                    )
                    if resp.status_code != 200:
                        print(f"Failed Edge Function for {b['booking_id']}: {resp.text}")

    except Exception as e:
        print(f"Error running send_reminders: {e}")

if __name__ == "__main__":
    asyncio.run(main())
