from fastapi import APIRouter, HTTPException
from app.supabase_client import supabase_admin

router = APIRouter(prefix="/concerts", tags=["concerts"])


@router.get("")
def list_concerts(city: str | None = None):
    """
    Returns all upcoming events, optionally filtered by city.
    Public endpoint - no login required, just like browsing BookMyShow.
    """
    query = supabase_admin.table("events").select("*")
    if city:
        query = query.eq("city", city)

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
