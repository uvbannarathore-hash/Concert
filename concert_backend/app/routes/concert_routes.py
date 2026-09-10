from fastapi import APIRouter, HTTPException
from app.supabase_client import supabase_admin

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
    query = supabase_admin.table("events").select("*, ticket_categories(price_inr)").eq("status", "Upcoming")
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
