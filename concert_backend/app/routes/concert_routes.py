import json
import logging
from fastapi import APIRouter, HTTPException, Depends
from app.supabase_client import supabase_admin
from app.auth import get_current_user

logger = logging.getLogger("concert_routes")

router = APIRouter(prefix="/concerts", tags=["concerts"])


@router.get("")
def list_concerts(
    city: str | None = None, 
    event_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None
):
    """
    Returns all upcoming events, optionally filtered by city, event_type, and dates.
    Public endpoint - no login required, just like browsing BookMyShow.
    """
    query = supabase_admin.table("events").select("*, ticket_categories(price_inr)").in_("status", ["Upcoming", "Sold Out"])
    if city:
        query = query.eq("city", city)
    if event_type:
        query = query.eq("event_type", event_type)
    if date_from:
        query = query.gte("event_date", date_from)
    if date_to:
        query = query.lte("event_date", date_to)

    result = query.execute()
    return {"events": result.data}


@router.get("/recommendations")
def get_recommendations(user: dict = Depends(get_current_user)):
    """
    Returns personalized event recommendations based on user's past bookings,
    wishlist, and positive reviews, using semantic similarity over pre-computed
    event embeddings.
    """
    user_id = user["user_id"]
    
    # 1. Fetch booked events (Confirmed & Paid)
    bookings_res = supabase_admin.table("bookings") \
        .select("event_id") \
        .eq("user_id", user_id) \
        .eq("status", "Confirmed") \
        .eq("payment_status", "Paid") \
        .order("created_at", desc=True) \
        .limit(10) \
        .execute()
    booked_event_ids = [b["event_id"] for b in (bookings_res.data or []) if b.get("event_id")]
    
    # 2. Fetch wishlist events
    wishlist_res = supabase_admin.table("wishlist") \
        .select("event_id") \
        .eq("user_id", user_id) \
        .order("added_at", desc=True) \
        .limit(10) \
        .execute()
    wishlist_event_ids = [w["event_id"] for w in (wishlist_res.data or []) if w.get("event_id")]
    
    # 3. Fetch positive reviews
    reviews_res = supabase_admin.table("reviews") \
        .select("event_id") \
        .eq("user_id", user_id) \
        .gte("rating", 4) \
        .order("created_at", desc=True) \
        .limit(10) \
        .execute()
    review_event_ids = [r["event_id"] for r in (reviews_res.data or []) if r.get("event_id")]
    
    # Combine signals into weighted map
    event_weights = {}
    for eid in booked_event_ids:
        event_weights[eid] = event_weights.get(eid, 0) + 3.0
    for eid in wishlist_event_ids:
        event_weights[eid] = event_weights.get(eid, 0) + 2.0
    for eid in review_event_ids:
        event_weights[eid] = event_weights.get(eid, 0) + 2.5
        
    unique_event_ids = list(event_weights.keys())
    
    FIELDS = (
        "event_id, artist_id, artist_name, venue_id, venue_name, city, "
        "event_date, event_time, event_type, status, image_url, "
        "latitude, longitude, description, "
        "ticket_categories(price_inr)"
    )
    
    # If we have signals, build a semantic profile
    if unique_event_ids:
        events_res = supabase_admin.table("events") \
            .select("event_id, embedding") \
            .in_("event_id", unique_event_ids) \
            .execute()
            
        embeddings_data = events_res.data or []
        
        vector_sum = [0.0] * 768
        total_weight = 0.0
        
        for e in embeddings_data:
            if not e.get("embedding"):
                continue
            try:
                emb_list = json.loads(e["embedding"]) if isinstance(e["embedding"], str) else e["embedding"]
                if len(emb_list) == 768:
                    weight = event_weights.get(e["event_id"], 1.0)
                    for i in range(768):
                        vector_sum[i] += emb_list[i] * weight
                    total_weight += weight
            except Exception as embed_err:
                logger.warning(f"Skipping malformed embedding for event {e.get('event_id')}: {embed_err}")
                
        if total_weight > 0:
            centroid = [v / total_weight for v in vector_sum]
            
            # Semantic search
            rpc_result = supabase_admin.rpc(
                "match_events",
                {
                    "query_embedding": centroid,
                    "match_threshold": 0.5,
                    "match_count": 20
                }
            ).execute()
            
            matches = rpc_result.data or []
            if matches:
                matched_event_ids = [m["event_id"] for m in matches]
                
                # Fetch full event details (excluding embedding)
                recs_res = supabase_admin.table("events") \
                    .select(FIELDS) \
                    .in_("event_id", matched_event_ids) \
                    .eq("status", "Upcoming") \
                    .execute()
                    
                current_events = {e["event_id"]: e for e in recs_res.data or []}
                
                # We don't need a separate query for all_booked_ids if we can just get all user bookings
                all_booked_res = supabase_admin.table("bookings") \
                    .select("event_id") \
                    .eq("user_id", user_id) \
                    .eq("status", "Confirmed") \
                    .eq("payment_status", "Paid") \
                    .execute()
                all_booked_ids = set(b["event_id"] for b in (all_booked_res.data or []) if b.get("event_id"))
                
                ranked_results = []
                for m in matches:
                    eid = m["event_id"]
                    if eid in current_events and eid not in all_booked_ids:
                        event_data = current_events[eid]
                        event_data["similarity_score"] = m["similarity"]
                        ranked_results.append(event_data)
                        if len(ranked_results) >= 10:
                            break
                            
                if ranked_results:
                    return {"results": ranked_results}
                    
    # Cold start / Fallback
    try:
        user_res = supabase_admin.table("users").select("city").eq("user_id", user_id).execute()
        city = user_res.data[0].get("city") if user_res.data else None
    except Exception:
        city = None
        
    query = supabase_admin.table("events").select(FIELDS).eq("status", "Upcoming")
    if city:
        query = query.eq("city", city)
    query = query.order("event_date", desc=False).limit(10)
    
    fallback_res = query.execute()
    fallback_events = fallback_res.data or []
    
    if not fallback_events and city:
        # Retry without city
        fallback_res = supabase_admin.table("events").select(FIELDS).eq("status", "Upcoming").order("event_date", desc=False).limit(10).execute()
        fallback_events = fallback_res.data or []
        
    try:
        all_booked_res = supabase_admin.table("bookings") \
            .select("event_id") \
            .eq("user_id", user_id) \
            .eq("status", "Confirmed") \
            .eq("payment_status", "Paid") \
            .execute()
        all_booked_ids = set(b["event_id"] for b in (all_booked_res.data or []) if b.get("event_id"))
    except Exception:
        all_booked_ids = set()
        
    final_fallback = []
    for e in fallback_events:
        if e["event_id"] not in all_booked_ids:
            e["similarity_score"] = 0.0
            final_fallback.append(e)
            
    return {"results": final_fallback[:10]}


@router.get("/{event_id}")
def get_concert_detail(event_id: str):
    """
    Returns a single event plus its ticket categories/pricing.
    """
    event = supabase_admin.table("events").select("*").eq("event_id", event_id).execute()
    if not event.data:
        raise HTTPException(status_code=404, detail="Event not found")

    tickets = (
        supabase_admin.table("ticket_categories")
        .select("*")
        .eq("event_id", event_id)
        .execute()
    )

    return {"event": event.data[0], "ticket_categories": tickets.data}


@router.get("/{event_id}/seats")
def get_event_seat_map(event_id: str):
    """
    Returns the full seat map for an event, grouped by row, for the
    interactive BookMyShow/PVR-style seat picker. If an event has no
    event_seats rows (admin hasn't built a seat layout for it), this
    returns an empty list - the frontend should fall back to the plain
    quantity-based booking flow in that case, not show an empty seat map.
    """
    seats = (
        supabase_admin.table("event_seats")
        .select("id, category, seat_row, seat_number, status")
        .eq("event_id", event_id)
        .order("seat_row")
        .order("seat_number")
        .execute()
    )
    return {"seats": seats.data, "has_seat_map": len(seats.data) > 0}