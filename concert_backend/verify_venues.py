import asyncio
from dotenv import load_dotenv
import os

load_dotenv()
from app.supabase_client import supabase_admin

def run_verification():
    print("--- VENUE MIGRATION VERIFICATION ---")
    
    # 1. Total venues
    v_res = supabase_admin.table("venues").select("*").execute()
    venues = v_res.data
    print(f"Total canonical venues created: {len(venues)}")
    
    # 2. Verify orphaned events = 0
    e_res = supabase_admin.table("events").select("event_id, venue_id").execute()
    events = e_res.data
    
    orphaned = 0
    valid = 0
    venue_ids = {v["venue_id"] for v in venues}
    for e in events:
        if e["venue_id"] not in venue_ids:
            orphaned += 1
            print(f"ORPHANED EVENT: {e['event_id']} with venue_id {e.get('venue_id')}")
        else:
            valid += 1
    
    print(f"Events properly mapped to valid venues: {valid}")
    print(f"Orphaned events: {orphaned}")
    
    # 3. Check DY Patil Stadium
    dy = [v for v in venues if "dy patil" in v["name"].lower()]
    print(f"\nDY Patil Stadium canonical venues ({len(dy)}):")
    for v in dy:
        print(f"  - ID: {v['venue_id']}, Name: '{v['name']}', City: '{v['city']}', Lat: {v.get('latitude')}, Lng: {v.get('longitude')}")
        
    # 4. Check TI Mall
    ti = [v for v in venues if "ti mall" in v["name"].lower()]
    print(f"\nTI Mall canonical venues ({len(ti)}):")
    for v in ti:
        print(f"  - ID: {v['venue_id']}, Name: '{v['name']}', City: '{v['city']}', Lat: {v.get('latitude')}, Lng: {v.get('longitude')}")

if __name__ == "__main__":
    run_verification()
