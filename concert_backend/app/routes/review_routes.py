from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from app.auth import get_current_user
from app.supabase_client import supabase_admin
from datetime import datetime, timezone
from dateutil import parser
import uuid

router = APIRouter(prefix="/reviews", tags=["reviews"])

class CreateReviewRequest(BaseModel):
    event_id: str
    rating: int = Field(..., ge=1, le=5)
    review_text: str | None = None

@router.post("")
def create_review(payload: CreateReviewRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]

    # 1. Verify that the user has a Paid & Confirmed booking for this event
    booking_res = (
        supabase_admin.table("bookings")
        .select("status, payment_status")
        .eq("user_id", user_id)
        .eq("event_id", payload.event_id)
        .execute()
    )
    
    if not booking_res.data:
        raise HTTPException(status_code=403, detail="You do not have a booking for this event.")
        
    has_valid_booking = any(
        b["status"] == "Confirmed" and b["payment_status"] == "Paid" 
        for b in booking_res.data
    )
    if not has_valid_booking:
        raise HTTPException(status_code=403, detail="Only paid and confirmed bookings are eligible for review.")

    # 2. Check if the event has ended (event_date and event_time are in the past)
    event_res = (
        supabase_admin.table("events")
        .select("event_date, event_time")
        .eq("event_id", payload.event_id)
        .execute()
    )
    if not event_res.data:
        raise HTTPException(status_code=404, detail="Event not found.")
        
    event_data = event_res.data[0]
    
    # Use timezone-aware datetime for current time
    now = datetime.now(timezone.utc)
    
    # Try parsing the event date and time
    # E.g., event_date="2026-09-11", event_time="19:00" or "7:00 PM"
    date_str = event_data.get("event_date")
    time_str = event_data.get("event_time", "00:00")
    
    if not date_str:
         raise HTTPException(status_code=400, detail="Event date is missing.")
         
    try:
        event_dt_naive = parser.parse(f"{date_str} {time_str}")
        # Assuming the events are stored/represented in local time or UTC. We will use timezone-aware for safety.
        # If the app implies local timezone, we assume the system local timezone or just compare naiively.
        # Let's make it UTC aware by default if no tz info is present, but typically Indian Standard Time or UTC is used.
        # The easiest safe comparison is to convert event_dt to UTC by treating it as local time, or just converting now() to local naive.
        now_naive = datetime.now()
        
        if now_naive < event_dt_naive:
            raise HTTPException(status_code=400, detail="You cannot review an event before it has ended.")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        # If parsing fails, fallback to strict string comparison for date only as a last resort
        print(f"Warning: Failed to parse event date/time: {e}")
        pass 

    # 3. Check for existing review (prevent duplicates)
    existing_review = (
        supabase_admin.table("reviews")
        .select("id")
        .eq("user_id", user_id)
        .eq("event_id", payload.event_id)
        .execute()
    )
    if existing_review.data:
        raise HTTPException(status_code=409, detail="You have already reviewed this event.")

    # 4. Insert the review
    try:
        supabase_admin.table("reviews").insert({
            "event_id": payload.event_id,
            "user_id": user_id,
            "rating": payload.rating,
            "review_text": payload.review_text
        }).execute()
        
        # Invalidate cache if review has text
        if payload.review_text and payload.review_text.strip():
            from app.services.summarization_service import invalidate_summary_cache
            invalidate_summary_cache(payload.event_id)
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to submit review: {str(e)}")

    return {"message": "Review submitted successfully."}

@router.get("/summary")
def get_review_summary_api(
    event_id: str | None = Query(None),
    artist_id: str | None = Query(None),
    venue_id: str | None = Query(None)
):
    from app.services.summarization_service import get_review_summary
    
    provided = [bool(x) for x in [event_id, artist_id, venue_id]]
    if sum(provided) != 1:
        raise HTTPException(status_code=400, detail="Provide exactly ONE of: event_id, artist_id, venue_id")
        
    if event_id:
        return get_review_summary("event", event_id)
    elif artist_id:
        return get_review_summary("artist", artist_id)
    elif venue_id:
        return get_review_summary("venue", venue_id)


@router.get("")
def get_reviews(
    event_id: str | None = Query(None),
    artist_id: str | None = Query(None),
    venue_id: str | None = Query(None)
):
    """
    Fetch reviews optionally filtered by event_id, artist_id, or venue_id.
    Aggregates user names and returns ratings.
    """
    if not any([event_id, artist_id, venue_id]):
        raise HTTPException(status_code=400, detail="Provide at least one filter (event_id, artist_id, venue_id)")
        
    query = supabase_admin.table("reviews").select("*, users(name), events(artist_id, venue_id, artist_name, venue_name)")
    
    if event_id:
        query = query.eq("event_id", event_id)
    # Note: If Supabase foreign table filtering isn't perfectly supported via PostgREST like this,
    # we might need to fetch events first or filter via RPC. 
    # For now, we will fetch events manually if artist_id or venue_id is provided, and then filter.
    
    if artist_id or venue_id:
        event_query = supabase_admin.table("events").select("event_id")
        if artist_id:
            event_query = event_query.eq("artist_id", artist_id)
        if venue_id:
            event_query = event_query.eq("venue_id", venue_id)
            
        events_res = event_query.execute()
        valid_event_ids = [e["event_id"] for e in events_res.data]
        
        if not valid_event_ids:
            return {"reviews": [], "average_rating": 0, "total_reviews": 0}
            
        query = query.in_("event_id", valid_event_ids)

    # Execute query
    reviews_res = query.order("created_at", desc=True).execute()
    reviews = reviews_res.data or []
    
    # Calculate aggregates
    total_reviews = len(reviews)
    average_rating = 0
    if total_reviews > 0:
        average_rating = sum(r["rating"] for r in reviews) / total_reviews
        
    return {
        "reviews": reviews,
        "average_rating": round(average_rating, 1),
        "total_reviews": total_reviews
    }
