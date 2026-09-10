from fastapi import APIRouter, HTTPException
from app.supabase_client import supabase_admin
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/venues", tags=["Venues"])

@router.get("")
def list_venues():
    try:
        res = supabase_admin.table("venues").select("*").execute()
        return {"venues": res.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{venue_id}")
def get_venue(venue_id: str):
    try:
        # Fetch venue details
        res = supabase_admin.table("venues").select("*").eq("venue_id", venue_id).execute()
        if not res.data:
            raise HTTPException(status_code=404, detail="Venue not found")
        
        venue = res.data[0]
        
        # Fetch events hosted at this venue
        events_res = supabase_admin.table("events").select(
            "event_id, artist_id, artist_name, venue_id, venue_name, city, event_date, event_time, status, image_url"
        ).eq("venue_id", venue_id).execute()
        
        events = events_res.data
        
        today = datetime.now().date().isoformat()
        
        upcoming_events = []
        past_events = []
        
        for e in events:
            if e.get("status") == "Cancelled":
                continue
                
            e_date = e.get("event_date", "")
            if e_date >= today or e.get("status") == "Available":
                upcoming_events.append(e)
            else:
                past_events.append(e)
                
        # Sort events by date
        upcoming_events.sort(key=lambda x: x.get("event_date", ""))
        past_events.sort(key=lambda x: x.get("event_date", ""), reverse=True)
        
        return {
            "venue": venue,
            "upcoming_events": upcoming_events,
            "past_events": past_events
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
