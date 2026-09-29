from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
import hashlib
from app.supabase_client import supabase_admin
from app.routes.organizer_routes import get_active_organizer_plan, get_current_organizer
from app.limiter import limiter
from datetime import datetime, timezone
import csv
from io import StringIO
from fastapi.responses import PlainTextResponse

router = APIRouter(prefix="/organizer/analytics", tags=["organizer_analytics"])

class UpdateTrackingRequest(BaseModel):
    ga_tracking_id: str | None = Field(None, pattern=r"^G-[A-Z0-9]{10}$")
    pixel_tracking_id: str | None = Field(None, pattern=r"^\d{15,16}$")

@router.patch("/events/{event_id}/tracking")
def update_event_tracking(event_id: str, payload: UpdateTrackingRequest, org: dict = Depends(get_active_organizer_plan)):
    if org["effective_plan_tier"] != "business":
        raise HTTPException(status_code=403, detail="Custom tracking IDs require the Business Plan.")
        
    res = supabase_admin.table("events").update({
        "ga_tracking_id": payload.ga_tracking_id,
        "pixel_tracking_id": payload.pixel_tracking_id
    }).eq("event_id", event_id).eq("organizer_id", org["user_id"]).execute()
    
    if not res.data:
        raise HTTPException(status_code=404, detail="Event not found or unauthorized")
        
    return {"message": "Tracking IDs updated successfully"}

class TrackPageViewRequest(BaseModel):
    event_id: str
    session_id: str

@router.post("/track-view")
@limiter.limit("10/minute")
def track_page_view(request: Request, payload: TrackPageViewRequest):
    """
    Public endpoint hit by the frontend to record an event page view.
    Rate limited and deduped via IP + Session + Date.
    """
    client_ip = request.client.host if request.client else "unknown"
    hashed_ip = hashlib.sha256(client_ip.encode('utf-8')).hexdigest()
    
    try:
        rpc_result = supabase_admin.rpc(
            "record_page_view",
            {
                "p_event_id": payload.event_id,
                "p_session_id": payload.session_id,
                "p_hashed_ip": hashed_ip,
                "p_max_ip_views": 50
            }
        ).execute()
        
        return rpc_result.data
    except Exception as e:
        # Since the RPC handles ON CONFLICT DO NOTHING internally and returns cleanly,
        # any exception here is a true internal error (network down, DB down, etc)
        raise HTTPException(status_code=500, detail="Internal tracking error")

@router.get("/events/{event_id}/export-attendees", response_class=PlainTextResponse)
def export_attendees_csv(event_id: str, org: dict = Depends(get_active_organizer_plan)):
    if org["effective_plan_tier"] not in ["pro", "business"]:
        raise HTTPException(status_code=403, detail="CSV Exports require the Pro or Business Plan.")
        
    # Explicitly check ownership using JOIN equivalent (Since PostgREST doesn't support complex JOINs natively without RPC, 
    # we first check ownership of the event)
    event_res = supabase_admin.table("events").select("event_id").eq("event_id", event_id).eq("organizer_id", org["user_id"]).execute()
    if not event_res.data:
        raise HTTPException(status_code=403, detail="Unauthorized: Not your event.")
        
    # Fetch confirmed bookings using the correct column names
    bookings_res = supabase_admin.table("bookings").select("booking_id, user_id, status, created_at, category, seats_booked, total_amount").eq("event_id", event_id).eq("status", "Confirmed").execute()
    bookings = bookings_res.data or []
    
    # Python-side JOIN for users
    user_ids = list(set(b["user_id"] for b in bookings if b.get("user_id")))
    user_map = {}
    if user_ids:
        users_res = supabase_admin.table("users").select("user_id, name, email, phone").in_("user_id", user_ids).execute()
        for u in (users_res.data or []):
            user_map[u["user_id"]] = u
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Booking ID", "Name", "Email", "Phone", "Category", "Quantity", "Total Price", "Date"])
    
    for row in bookings:
        user = user_map.get(row.get("user_id"), {})
        writer.writerow([
            row.get("booking_id"),
            user.get("name", "Unknown"),
            user.get("email", ""),
            user.get("phone", ""),
            row.get("category", ""),
            row.get("seats_booked", ""),
            row.get("total_amount", ""),
            row.get("created_at", "")
        ])
        
    return output.getvalue()

@router.get("/events/{event_id}/stats")
def get_event_stats(event_id: str, org: dict = Depends(get_active_organizer_plan)):
    # Verify ownership
    event_res = supabase_admin.table("events").select("event_id").eq("event_id", event_id).eq("organizer_id", org["user_id"]).execute()
    if not event_res.data:
        raise HTTPException(status_code=403, detail="Unauthorized")
        
    # Get categories to calculate total capacity & remaining
    cat_res = supabase_admin.table("ticket_categories").select("total_seats, available_seats").eq("event_id", event_id).execute()
    total_capacity = sum((c.get("total_seats") or 0) for c in (cat_res.data or []))
    remaining = sum((c.get("available_seats") or 0) for c in (cat_res.data or []))
    
    # Get bookings for sales & cancellations
    bookings_res = supabase_admin.table("bookings").select("status, seats_booked, total_amount").eq("event_id", event_id).execute()
    bookings = bookings_res.data or []
    
    confirmed = [b for b in bookings if b.get("status") == "Confirmed"]
    cancelled = [b for b in bookings if b.get("status") == "Cancelled"]
    
    total_sold = sum((b.get("seats_booked") or 0) for b in confirmed)
    total_revenue = sum((b.get("total_amount") or 0.0) for b in confirmed)
    cancellations = sum((b.get("seats_booked") or 0) for b in cancelled)
    
    return {
        "total_capacity": total_capacity,
        "remaining_seats": remaining,
        "total_tickets_sold": total_sold,
        "total_revenue": total_revenue,
        "cancellations": cancellations,
        "total_confirmed_orders": len(confirmed)
    }
