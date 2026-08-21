import time
import httpx
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from app.admin_auth import get_current_admin
from app.supabase_client import supabase_admin
from app.config import N8N_ADMIN_WEBHOOK_URL

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------- Admin AI Assistant ----------

@router.post("/agent-chat")
async def admin_chat(
    message: str = Form(...),
    image: UploadFile = File(None),
    admin=Depends(get_current_admin),
):
    """
    Forwards the admin's message to the n8n Admin Assistant webhook.

    get_current_admin has ALREADY verified this request comes from a real,
    logged-in admin (is_admin=true) before this function even runs - the
    n8n Admin Assistant workflow itself does not re-check permissions, it
    trusts that this backend route is the only thing allowed to call it.

    If an image is attached (e.g. an event poster), it is uploaded to the
    Supabase "event-images" storage bucket first, and its public URL is
    embedded into the message text as "[Uploaded image URL: ...]" before
    forwarding to n8n. The AI Agent in n8n is instructed to detect this
    marker and pass the URL along when creating/updating an event.
    """
    if not N8N_ADMIN_WEBHOOK_URL:
        raise HTTPException(
            status_code=500,
            detail="Admin assistant is not configured (N8N_ADMIN_WEBHOOK_URL missing)",
        )

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

        enriched_message = f"{message} [Uploaded image URL: {public_url}]"

    body = {
        "admin_user_id": admin["user_id"],
        "message": enriched_message,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(N8N_ADMIN_WEBHOOK_URL, json=body)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Failed to reach admin assistant: {e}")

        if not response.text.strip():
            raise HTTPException(
                status_code=502,
                detail="Admin assistant (n8n) returned an empty response. "
                       "Check that the n8n workflow is Active/Published and that "
                       "N8N_ADMIN_WEBHOOK_URL points to the production webhook, not the test one.",
            )

        try:
            return response.json()
        except ValueError:
            raise HTTPException(
                status_code=502,
                detail=f"Admin assistant returned invalid JSON: {response.text[:300]}",
            )


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
    result = supabase_admin.table("bookings").select("*").order("created_at", desc=True).execute()
    return {"bookings": result.data}