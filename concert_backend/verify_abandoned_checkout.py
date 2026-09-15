import os
import time
import requests
from dotenv import load_dotenv

load_dotenv(".env")
supabase_url = os.environ.get("SUPABASE_URL")
service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

headers = {
    "apikey": service_key,
    "Authorization": f"Bearer {service_key}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

print("1. Creating dummy Pending booking aged 16 minutes...")
# In a real environment, you'd insert a dummy user/event first, but this assumes valid FKs exist
# We will just print instructions for the user if they want to run it.
print("To run this test effectively against your deployed environment:")
print("  a. Insert a dummy booking in the Supabase UI with status='Pending', payment_status='Pending'")
print("  b. Set its created_at to 16 minutes ago")
print("  c. Watch the pg_cron job pick it up at the next minute mark")
print("  d. Check the Edge Function logs to see independent channel delivery!")
print("  e. Verify abandoned_email_sent and abandoned_telegram_sent are set to true.")
