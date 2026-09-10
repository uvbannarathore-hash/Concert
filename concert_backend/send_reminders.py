import asyncio
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import os

load_dotenv()

from app.supabase_client import supabase_admin

async def main():
    print("Running send_reminders cron job...")
    
    # Calculate the time window for 24 hours from now
    now = datetime.now(timezone.utc)
    target_time_start = now + timedelta(hours=23)
    target_time_end = now + timedelta(hours=25)
    
    # Convert dates for the DB query format
    date_start_str = target_time_start.strftime("%Y-%m-%d")
    date_end_str = target_time_end.strftime("%Y-%m-%d")

    try:
        # Find all upcoming events occurring tomorrow
        # (This uses a simplistic date-based filter, a more precise time-based 
        # approach could be added if event_time is strictly formatted)
        events_res = supabase_admin.table("events").select("event_id, event_date").gte("event_date", date_start_str).lte("event_date", date_end_str).execute()
        
        events = events_res.data
        if not events:
            print("No events found in the target window.")
            return

        event_ids = [evt["event_id"] for evt in events]
        print(f"Found {len(event_ids)} events happening tomorrow: {event_ids}")

        # Find confirmed bookings for these events that haven't received a reminder yet
        bookings_res = supabase_admin.table("bookings").select("booking_id").eq("status", "Confirmed").eq("reminder_sent", False).in_("event_id", event_ids).execute()
        
        bookings = bookings_res.data
        if not bookings:
            print("No eligible bookings found that need reminders.")
            return
            
        booking_ids = [b["booking_id"] for b in bookings]
        print(f"Found {len(booking_ids)} bookings to send reminders to.")

        # Update them all to trigger the Webhook + Edge Function
        update_res = supabase_admin.table("bookings").update({"reminder_sent": True}).in_("booking_id", booking_ids).execute()
        
        print(f"Successfully triggered {len(update_res.data)} reminders.")

    except Exception as e:
        print(f"Error running send_reminders: {e}")

if __name__ == "__main__":
    asyncio.run(main())
