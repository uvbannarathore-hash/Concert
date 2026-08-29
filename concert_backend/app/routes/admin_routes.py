import time
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from app.admin_auth import get_current_admin
from app.supabase_client import supabase_admin
from app.agents import admin_agent

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------- Admin AI Assistant ----------

@router.post("/agent-chat")
async def admin_chat(
    message: str = Form(...),
    image: UploadFile = File(None),
    latitude: float = Form(None),
    longitude: float = Form(None),
    session_id: str = Form(None),
    admin=Depends(get_current_admin),
):
    """
    Runs the admin assistant natively (see app/agents/admin_agent.py) - no
    longer forwards to n8n.

    get_current_admin has ALREADY verified this request comes from a real,
    logged-in admin (is_admin=true) before this function even runs.

    If an image is attached (e.g. an event poster), it is uploaded to the
    Supabase "event-images" storage bucket first, and its public URL is
    embedded into the message text as "[Uploaded image URL: ...]" - the
    admin agent's system prompt is instructed to detect this marker and
    pass the URL along when creating/updating an event.

    If a venue location (latitude/longitude) is attached - e.g. picked via
    Google Places Autocomplete on the frontend - it's embedded the same way
    as "[Venue Location: lat,lng]" (this used to be done by n8n's "Enrich
    With Location" node - now done directly here since there's no
    intermediate workflow anymore).

    session_id: identifies ONE conversation/chat window, distinct from
    admin_user_id (which identifies WHO is chatting) - see
    app/agents/memory.py. Falls back to admin_user_id if not provided, so
    older frontend builds without the "New Chat" session_id fix still work,
    just without per-conversation isolation.
    """
    enriched_message = message

    if image is not None:
        file_bytes = await image.read()
        # unique filename so re-uploads never collide
        safe_name = image.filename.replace(" ", "_")
        filename = f"{int(time.time())}_{safe_name}"

        try:
            supabase_admin.storage.from_("event-images").upload(
                path=filename,
                file=file_bytes,
                file_options={
                    "content-type": image.content_type or "application/octet-stream",
                    "upsert": "true",
                },
            )
            public_url_response = supabase_admin.storage.from_("event-images").get_public_url(filename)

            # supabase-py v2 returns a plain string; older v1 clients sometimes
            # return a dict like {"publicURL": "..."} - handle both safely.
            if isinstance(public_url_response, str):
                public_url = public_url_response
            elif isinstance(public_url_response, dict):
                public_url = public_url_response.get("publicURL") or public_url_response.get("publicUrl")
            else:
                public_url = str(public_url_response)

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Image upload failed: {e}")

        enriched_message = f"{enriched_message} [Uploaded image URL: {public_url}]"

    if latitude is not None and longitude is not None:
        enriched_message = f"{enriched_message} [Venue Location: {latitude},{longitude}]"

    effective_session_id = session_id or admin["user_id"]

    reply = await admin_agent.handle_message(
        admin_user_id=admin["user_id"],
        session_id=effective_session_id,
        message=enriched_message,
    )
    return {"reply": reply}


# ---------- Events ----------

class CreateEventRequest(BaseModel):
    artist_id: str
    artist_name: str
    venue_id: str
    venue_name: str
    city: str
    event_date: str   # "2026-12-20"
    event_time: str   # "7:00 PM"
    event_type: str = "Concert"  # Concert | Movie | Comedy Show | Music Show | Play | Sports
    latitude: float | None = None
    longitude: float | None = None


@router.post("/events")
def create_event(payload: CreateEventRequest, admin=Depends(get_current_admin)):
    event_id = f"EVT{int(time.time())}"
    supabase_admin.table("events").insert(
        {
            "event_id": event_id,
            "artist_id": payload.artist_id,
            "artist_name": payload.artist_name,
            "venue_id": payload.venue_id,
            "venue_name": payload.venue_name,
            "city": payload.city,
            "event_date": payload.event_date,
            "event_time": payload.event_time,
            "event_type": payload.event_type,
            "status": "Upcoming",
            "latitude": payload.latitude,
            "longitude": payload.longitude,
        }
    ).execute()
    return {"message": "Event created", "event_id": event_id}


class UpdateEventStatusRequest(BaseModel):
    status: str  # Upcoming | Sold Out | Cancelled | Completed


@router.patch("/events/{event_id}/status")
def update_event_status(event_id: str, payload: UpdateEventStatusRequest, admin=Depends(get_current_admin)):
    result = (
        supabase_admin.table("events")
        .update({"status": payload.status})
        .eq("event_id", event_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"message": "Event status updated"}


# ---------- Ticket categories / pricing ----------

class AddTicketCategoryRequest(BaseModel):
    event_id: str
    category: str
    price_inr: float
    total_seats: int


@router.post("/ticket-categories")
def add_ticket_category(payload: AddTicketCategoryRequest, admin=Depends(get_current_admin)):
    supabase_admin.table("ticket_categories").insert(
        {
            "event_id": payload.event_id,
            "category": payload.category,
            "price_inr": payload.price_inr,
            "total_seats": payload.total_seats,
            "available_seats": payload.total_seats,
        }
    ).execute()
    return {"message": "Ticket category added"}


class UpdatePricingRequest(BaseModel):
    price_inr: float


@router.patch("/ticket-categories/{event_id}/{category}")
def update_pricing(event_id: str, category: str, payload: UpdatePricingRequest, admin=Depends(get_current_admin)):
    result = (
        supabase_admin.table("ticket_categories")
        .update({"price_inr": payload.price_inr})
        .eq("event_id", event_id)
        .eq("category", category)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Ticket category not found")
    return {"message": "Price updated"}


# ---------- Dashboard-style read (all bookings across all users) ----------

@router.get("/bookings")
def list_all_bookings(admin=Depends(get_current_admin)):
    result = supabase_admin.table("bookings").select("*, events(*)").order("created_at", desc=True).execute()
    return {"bookings": result.data}