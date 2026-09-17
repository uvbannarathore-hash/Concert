import sys
import os

# Ensure we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.supabase_client import supabase_admin

print("--- Checking Batwara Events ---")
batwara_events = supabase_admin.table("events").select("event_id, artist_id, artist_name, description").ilike("artist_name", "%Batwara%").execute()
for e in batwara_events.data:
    print(f"[{e['event_id']}] Artist: {e['artist_name']} | Desc: {str(e['description'])[:50]}")

print("\n--- Checking Other Events ---")
other_events = supabase_admin.table("events").select("event_id, artist_id, artist_name, description").limit(10).execute()
for e in other_events.data:
    print(f"[{e['event_id']}] Artist: {e['artist_name']} | Desc: {str(e['description'])[:50]}")
