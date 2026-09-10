from fastapi import APIRouter, HTTPException
from app.supabase_client import supabase_admin

router = APIRouter(prefix="/artists", tags=["artists"])

@router.get("")
def list_artists():
    """Public endpoint to list all artists"""
    result = supabase_admin.table("artists").select("*").order("name").execute()
    return {"artists": result.data}

@router.get("/{artist_id}")
def get_artist(artist_id: str):
    """Public endpoint to get an artist profile and their events"""
    artist_res = supabase_admin.table("artists").select("*").eq("artist_id", artist_id).execute()
    if not artist_res.data:
        raise HTTPException(status_code=404, detail="Artist not found")
        
    artist = artist_res.data[0]
    
    # Fetch events for this artist, excluding Cancelled
    events_res = supabase_admin.table("events").select("*").eq("artist_id", artist_id).neq("status", "Cancelled").order("event_date").execute()
    events = events_res.data
    
    upcoming_events = [e for e in events if e.get("status") != "Completed"]
    past_events = [e for e in events if e.get("status") == "Completed"]
    
    artist["upcoming_events"] = upcoming_events
    artist["past_events"] = past_events
    
    return {"artist": artist}
