import time
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.admin_auth import get_current_admin
from app.supabase_client import supabase_admin
from app.config import N8N_ADMIN_WEBHOOK_URL

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------- Admin AI Assistant ----------

class AdminChatRequest(BaseModel):
    message: str


@router.post("/agent-chat")
async def admin_chat(payload: AdminChatRequest, admin=Depends(get_current_admin)):
    """
    Forwards the admin's message to the n8n Admin Assistant webhook.

    get_current_admin has ALREADY verified this request comes from a real,
    logged-in admin (is_admin=true) before this function even runs - the
    n8n Admin Assistant workflow itself does not re-check permissions, it
    trusts that this backend route is the only thing allowed to call it.
    """
    if not N8N_ADMIN_WEBHOOK_URL:
        raise HTTPException(status_code=500, detail="Admin assistant is not configured (N8N_ADMIN_WEBHOOK_URL missing)")

    body = {
        "admin_user_id": admin["user_id"],
        "message": payload.message,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(N8N_ADMIN_WEBHOOK_URL, json=body)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Failed to reach admin assistant: {e}")

    return response.json()


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
