import asyncio
from dotenv import load_dotenv
import os

load_dotenv()
from app.supabase_client import supabase_admin

def run():
    print("Fetching events from Supabase...")
    res = supabase_admin.table("events").select("event_id, venue_id, venue_name, city, latitude, longitude").execute()
    events = res.data
    
    if not events:
        print("No events found in the database.")
        return
        
    print(f"Total events fetched: {len(events)}\n")
    
    null_ids = []
    null_names = []
    name_to_ids = {}
    id_to_names = {}
    
    for ev in events:
        eid = ev.get("event_id")
        vid = ev.get("venue_id")
        vname = ev.get("venue_name")
        
        if not vid or not vid.strip():
            null_ids.append(eid)
            
        if not vname or not vname.strip():
            null_names.append(eid)
            
        if vname:
            # normalize for checking
            normalized = vname.strip().lower()
            if normalized not in name_to_ids:
                name_to_ids[normalized] = set()
            if vid:
                name_to_ids[normalized].add(vid)
                
        if vid:
            if vid not in id_to_names:
                id_to_names[vid] = set()
            if vname:
                id_to_names[vid].add(vname)
                
    print("--- NULL/EMPTY CHECKS ---")
    print(f"Events with NULL/empty venue_id: {len(null_ids)}")
    print(f"Events with NULL/empty venue_name: {len(null_names)}")
    
    print("\n--- NORMALIZED NAME TO MULTIPLE IDs ---")
    multiple_ids = {name: ids for name, ids in name_to_ids.items() if len(ids) > 1}
    if not multiple_ids:
        print("No normalized venue name points to multiple venue_ids.")
    else:
        for name, ids in multiple_ids.items():
            print(f"Name '{name}' maps to IDs: {ids}")
            
    print("\n--- EXACT RAW DATA DUMP (VENUES) ---")
    for ev in events:
        print(f"Event: {ev['event_id']}, Venue ID: '{ev.get('venue_id')}', Venue Name: '{ev.get('venue_name')}', City: '{ev.get('city')}', Lat: {ev.get('latitude')}, Lng: {ev.get('longitude')}")

if __name__ == "__main__":
    run()
