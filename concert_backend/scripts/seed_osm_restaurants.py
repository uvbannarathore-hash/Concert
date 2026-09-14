import os
import sys
import httpx
import time
import math
import argparse
from supabase import create_client
from dotenv import load_dotenv

# Add the app directory to the Python path if running from root
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("Error: SUPABASE_URL and SUPABASE_SERVICE_KEY environment variables are required.")
    sys.exit(1)

supabase_admin = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return 6371 * c

def fetch_and_store_restaurants_for_venue(lat: float, lon: float, radius: int = 2000):
    overpass_url = "https://overpass-api.de/api/interpreter"
    
    query = f"""
    [out:json][timeout:25];
    (
      node["amenity"="restaurant"](around:{radius},{lat},{lon});
      node["amenity"="cafe"](around:{radius},{lat},{lon});
    );
    out body;
    """
    
    print(f"Fetching restaurants near ({lat}, {lon}) from Overpass API...")
    
    max_retries = 1
    for attempt in range(max_retries + 1):
        try:
            resp = httpx.post(
                overpass_url,
                content=query.strip(),
                headers={"Content-Type": "text/plain", "User-Agent": "ConcertAppSeedScript/1.0"},
                timeout=30.0
            )
            
            if resp.status_code in (429, 504):
                if attempt < max_retries:
                    print(f"Received {resp.status_code}. Retrying in 15 seconds...")
                    time.sleep(15)
                    continue
                else:
                    return {"status": "error", "code": resp.status_code, "msg": f"Failed after retry with {resp.status_code}"}
                    
            resp.raise_for_status()
            data = resp.json()
            elements = data.get("elements", [])
            
            restaurants_to_insert = []
            for el in elements:
                tags = el.get("tags", {})
                name = tags.get("name")
                if not name:
                    continue
                    
                cuisine = tags.get("cuisine", "Mixed")
                el_lat = el.get("lat")
                el_lon = el.get("lon")
                osm_id = el.get("id")
                
                if el_lat is None or el_lon is None or osm_id is None:
                    continue
                    
                # Map cost deterministically
                base_cost = (len(name) * 100) % 2000 + 400
                
                restaurants_to_insert.append({
                    "osm_id": osm_id,
                    "name": name,
                    "cuisine": cuisine,
                    "latitude": el_lat,
                    "longitude": el_lon,
                    "estimated_cost_for_two_inr": base_cost,
                    "source": "osm"
                })
                
            if not restaurants_to_insert:
                print(f"No restaurants found near ({lat}, {lon}).")
                return {"status": "empty", "found": 0, "upserted": 0}
                
            print(f"Found {len(restaurants_to_insert)} restaurants. Upserting to Supabase...")
            
            upserted_count = 0
            chunk_size = 100
            for i in range(0, len(restaurants_to_insert), chunk_size):
                chunk = restaurants_to_insert[i:i + chunk_size]
                supabase_admin.table("restaurants").upsert(
                    chunk, on_conflict="osm_id"
                ).execute()
                upserted_count += len(chunk)
                
            print(f"Upserted {upserted_count} records.")
            return {"status": "success", "found": len(restaurants_to_insert), "upserted": upserted_count}
                
        except Exception as e:
            if attempt < max_retries:
                print(f"Error: {e}. Retrying in 15 seconds...")
                time.sleep(15)
            else:
                return {"status": "error", "code": 500, "msg": str(e)}

def main():
    parser = argparse.ArgumentParser(description="Seed OSM restaurants to Supabase cache.")
    parser.add_argument("--venue-id", type=str, help="Target specific venue ID for seeding.")
    args = parser.parse_args()

    target_venue_id = args.venue_id
    deduped_coords = []

    if target_venue_id:
        print(f"Targeting venue ID: {target_venue_id}...")
        
        # Check venues table first
        v_result = supabase_admin.table("venues").select("latitude, longitude").eq("venue_id", target_venue_id).execute()
        if v_result.data and v_result.data[0].get("latitude") is not None:
            lat = float(v_result.data[0]["latitude"])
            lon = float(v_result.data[0]["longitude"])
            deduped_coords.append((lat, lon))
        else:
            # Check events table fallback
            e_result = supabase_admin.table("events").select("latitude, longitude").eq("venue_id", target_venue_id).execute()
            if e_result.data and e_result.data[0].get("latitude") is not None:
                lat = float(e_result.data[0]["latitude"])
                lon = float(e_result.data[0]["longitude"])
                deduped_coords.append((lat, lon))
            else:
                print(f"Error: Could not resolve valid coordinates for venue_id '{target_venue_id}'.")
                sys.exit(1)
        print(f"Resolved target area to ({deduped_coords[0][0]}, {deduped_coords[0][1]})")
    else:
        print("Fetching distinct venues from Supabase...")
        events_result = supabase_admin.table("events").select("latitude, longitude").execute()
        
        unique_coords = set()
        if events_result.data:
            for row in events_result.data:
                lat = row.get("latitude")
                lon = row.get("longitude")
                if lat is not None and lon is not None:
                    unique_coords.add((float(lat), float(lon)))
                    
        venues_result = supabase_admin.table("venues").select("latitude, longitude").execute()
        if venues_result.data:
            for row in venues_result.data:
                lat = row.get("latitude")
                lon = row.get("longitude")
                if lat is not None and lon is not None:
                    unique_coords.add((float(lat), float(lon)))
                    
        print(f"Found {len(unique_coords)} unique venue coordinates.")
        
        # Deduplicate coords within 2km
        for lat, lon in unique_coords:
            is_duplicate = False
            for d_lat, d_lon in deduped_coords:
                if haversine(lat, lon, d_lat, d_lon) < 2.0:
                    is_duplicate = True
                    break
            if not is_duplicate:
                deduped_coords.append((lat, lon))
                
        print(f"Deduplicated to {len(deduped_coords)} distinct areas for querying.")
    
    stats = {
        "processed": 0,
        "success": 0,
        "empty": 0,
        "failed": 0,
        "found": 0,
        "upserted": 0,
        "429": 0,
        "504": 0
    }
    
    for idx, (lat, lon) in enumerate(deduped_coords):
        if not target_venue_id and idx > 0:
            print("Waiting 15 seconds before next Overpass request to respect rate limits...")
            time.sleep(15)
            
        stats["processed"] += 1
        res = fetch_and_store_restaurants_for_venue(lat, lon)
        
        if target_venue_id:
            result_label = "SUCCESS"
            if res["status"] == "empty":
                result_label = "NO_RESTAURANTS"
            elif res["status"] == "error":
                result_label = "FAILED"
            print(f"Targeted seed result for {target_venue_id}: {result_label}")
            
        if res["status"] == "success":
            stats["success"] += 1
            stats["found"] += res["found"]
            stats["upserted"] += res["upserted"]
        elif res["status"] == "empty":
            stats["empty"] += 1
        else:
            stats["failed"] += 1
            if res.get("code") == 429:
                stats["429"] += 1
            elif res.get("code") == 504:
                stats["504"] += 1
            print(f"Failed: {res.get('msg')}")
            
    print("\n=== FINAL SUMMARY ===")
    print(f"Venues/areas processed: {stats['processed']}")
    print(f"Successful queries: {stats['success']}")
    print(f"Failed queries: {stats['failed']}")
    print(f"No restaurants found: {stats['empty']}")
    print(f"Restaurants found: {stats['found']}")
    print(f"Restaurants upserted: {stats['upserted']}")
    print(f"429 count: {stats['429']}")
    print(f"504 count: {stats['504']}")
    print("=====================")

if __name__ == "__main__":
    main()
