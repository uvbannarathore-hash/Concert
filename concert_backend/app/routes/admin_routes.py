import time
import uuid
import hashlib
import logging
from datetime import datetime
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, Dict
from app.admin_auth import get_current_admin
from app.supabase_client import supabase_admin
from app.agents import admin_agent
from app.services import embedding_service

logger = logging.getLogger("admin_routes")

router = APIRouter(prefix="/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Embedding helper — called as a BackgroundTask after event creation/update
# ---------------------------------------------------------------------------

def _generate_and_store_embedding(event_id: str, event_data: dict):
    """
    Generates a Gemini Embedding 2 (768-dim) embedding for the event and
    stores it in events.embedding. Called as a background task so it never
    blocks the HTTP response. Failures are logged; event creation still
    succeeds even if embedding generation fails.
    """
    try:
        vector = embedding_service.generate_event_embedding(event_data)
        if vector:
            supabase_admin.table("events") \
                .update({"embedding": vector}) \
                .eq("event_id", event_id) \
                .execute()
            logger.info(f"Embedding stored for event {event_id}")
        else:
            logger.warning(f"Embedding generation returned None for event {event_id}")
    except Exception as exc:
        logger.error(f"Failed to store embedding for event {event_id}: {exc}")




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
    description: str | None = None
    latitude: float | None = None
    longitude: float | None = None


@router.post("/events")
def create_event(payload: CreateEventRequest, background_tasks: BackgroundTasks, admin=Depends(get_current_admin)):
    normalized_venue_name = payload.venue_name.strip()
    normalized_city = payload.city.strip()
    
    venue_res = supabase_admin.table("venues").select("venue_id").ilike("name", normalized_venue_name).ilike("city", normalized_city).execute()
    if venue_res.data:
        venue_id = venue_res.data[0]["venue_id"]
    else:
        v_hash = hashlib.md5((normalized_venue_name.lower() + normalized_city.lower()).encode('utf-8')).hexdigest()
        venue_id = f"VEN_{v_hash[:10].upper()}"
        supabase_admin.table("venues").insert({
            "venue_id": venue_id,
            "name": normalized_venue_name,
            "city": normalized_city,
            "latitude": payload.latitude,
            "longitude": payload.longitude,
        }).execute()

    event_id = f"EVT{uuid.uuid4().hex[:12]}"
    event_row = {
        "event_id": event_id,
        "artist_id": payload.artist_id,
        "artist_name": payload.artist_name,
        "venue_id": venue_id,
        "venue_name": payload.venue_name,
        "city": payload.city,
        "event_date": payload.event_date,
        "event_time": payload.event_time,
        "event_type": payload.event_type,
        "description": payload.description,
        "status": "Upcoming",
        "latitude": payload.latitude,
        "longitude": payload.longitude,
    }
    supabase_admin.table("events").insert(event_row).execute()
    background_tasks.add_task(_generate_and_store_embedding, event_id, event_row)
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


# ---------- "List Your Show" review queue ----------
# Organizer-facing submit/track endpoints live in show_routes.py. These are
# the admin-side review actions: list pending submissions, approve (which
# converts a submission into a real event via the SAME
# create_event_with_pricing RPC the admin AI assistant uses), or reject
# with a reason the organizer can see on their end.

@router.get("/show-submissions")
def list_show_submissions(status: str = "Pending", admin=Depends(get_current_admin)):
    """status: Pending (default), Approved, Rejected, or 'all' for every submission."""
    query = supabase_admin.table("show_submissions").select("*, users(name, email, phone)").order("created_at", desc=True)
    if status != "all":
        query = query.eq("status", status)
    result = query.execute()
    return {"submissions": result.data}


@router.post("/show-submissions/{submission_id}/approve")
def approve_show_submission(submission_id: int, background_tasks: BackgroundTasks, admin=Depends(get_current_admin)):
    """
    Converts a pending submission into a real, live event. Uses the exact
    same create_event_with_pricing RPC as the admin AI assistant's
    create_event1 tool, so a "List Your Show" approval and an admin
    creating an event via chat produce identically-shaped events - there
    is no second, parallel event-creation code path to keep in sync.
    """
    submission = (
        supabase_admin.table("show_submissions")
        .select("*")
        .eq("id", submission_id)
        .execute()
    )
    if not submission.data:
        raise HTTPException(status_code=404, detail="Submission not found")

    row = submission.data[0]
    if row["status"] != "Pending":
        raise HTTPException(status_code=400, detail=f"Submission is already {row['status']}, not Pending")

    event_id = f"EVT{uuid.uuid4().hex[:12]}"
    
    normalized_artist_name = row["artist_name"].strip()
    artist_res = supabase_admin.table("artists").select("artist_id").eq("name", normalized_artist_name).execute()
    
    if artist_res.data:
        artist_id = artist_res.data[0]["artist_id"]
    else:
        hash_str = hashlib.md5(normalized_artist_name.lower().encode('utf-8')).hexdigest()
        artist_id = f"ART_{hash_str[:10].upper()}"
        supabase_admin.table("artists").insert({
            "artist_id": artist_id,
            "name": normalized_artist_name,
        }).execute()
        
    normalized_venue_name = row["venue_name"].strip()
    normalized_city = row["city"].strip()
    
    venue_res = supabase_admin.table("venues").select("venue_id").ilike("name", normalized_venue_name).ilike("city", normalized_city).execute()
    if venue_res.data:
        venue_id = venue_res.data[0]["venue_id"]
    else:
        v_hash = hashlib.md5((normalized_venue_name.lower() + normalized_city.lower()).encode('utf-8')).hexdigest()
        venue_id = f"VEN_{v_hash[:10].upper()}"
        supabase_admin.table("venues").insert({
            "venue_id": venue_id,
            "name": normalized_venue_name,
            "city": normalized_city,
            "latitude": row.get("latitude"),
            "longitude": row.get("longitude"),
        }).execute()

    rpc_result = supabase_admin.rpc(
        "create_event_with_pricing",
        {
            "p_event_id": event_id,
            "p_artist_id": artist_id,
            "p_artist_name": row["artist_name"],
            "p_venue_id": venue_id,
            "p_venue_name": row["venue_name"],
            "p_city": row["city"],
            "p_event_date": row["event_date"],
            "p_event_time": row["event_time"],
            "p_event_type": row["event_type"],
            "p_categories": row["categories"],
            "p_image_url": row.get("image_url"),
            "p_latitude": row.get("latitude"),
            "p_longitude": row.get("longitude"),
        },
    ).execute()

    if not rpc_result.data or not rpc_result.data.get("event_id"):
        raise HTTPException(status_code=500, detail="Failed to create event from submission")

    supabase_admin.table("show_submissions").update(
        {
            "status": "Approved",
            "reviewed_by": admin["user_id"],
            "reviewed_at": "now()",
            "created_event_id": event_id,
        }
    ).eq("id", submission_id).execute()

    # Schedule embedding generation in background (consistent with create_event)
    event_row_for_embedding = {
        "event_id": event_id,
        "artist_name": row["artist_name"],
        "venue_name": row["venue_name"],
        "city": row["city"],
        "event_date": row["event_date"],
        "event_time": row["event_time"],
        "event_type": row["event_type"],
        "description": None,
    }
    background_tasks.add_task(_generate_and_store_embedding, event_id, event_row_for_embedding)

    return {"message": "Submission approved and published", "event_id": event_id}


class RejectSubmissionRequest(BaseModel):
    reason: str


@router.post("/show-submissions/{submission_id}/reject")
def reject_show_submission(submission_id: int, payload: RejectSubmissionRequest, admin=Depends(get_current_admin)):
    result = (
        supabase_admin.table("show_submissions")
        .update(
            {
                "status": "Rejected",
                "rejection_reason": payload.reason,
                "reviewed_by": admin["user_id"],
                "reviewed_at": "now()",
            }
        )
        .eq("id", submission_id)
        .eq("status", "Pending")
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Pending submission not found")
    return {"message": "Submission rejected"}


# ---------- Seat layout builder ----------
# Lets an admin define the physical seat map for an event, one row at a
# time (matching the PVR/BookMyShow reference UI: row P = Recliner,
# rows N/M/L = Prime, etc.). Calling this for an event is what turns ON
# the interactive seat-map booking experience for it - events with zero
# event_seats rows keep using the plain quantity-based booking flow.

class SeatRowRequest(BaseModel):
    event_id: str
    category: str
    seat_row: str
    seat_count: int
    start_number: int = 1


@router.post("/seat-layout/add-row")
def add_seat_row(payload: SeatRowRequest, admin=Depends(get_current_admin)):
    result = supabase_admin.rpc(
        "generate_seat_row",
        {
            "p_event_id": payload.event_id,
            "p_category": payload.category,
            "p_seat_row": payload.seat_row,
            "p_seat_count": payload.seat_count,
            "p_start_number": payload.start_number,
        },
    ).execute()
    return result.data


@router.get("/seat-layout/{event_id}")
def get_seat_layout(event_id: str, admin=Depends(get_current_admin)):
    """Returns the current seat layout for an event, row by row, so the
    admin can see what's already been defined before adding more rows."""
    result = (
        supabase_admin.table("event_seats")
        .select("id, category, seat_row, seat_number, status")
        .eq("event_id", event_id)
        .order("seat_row")
        .order("seat_number")
        .execute()
    )
    return {"seats": result.data}


@router.delete("/seat-layout/{event_id}/row/{seat_row}")
def delete_seat_row(event_id: str, seat_row: str, admin=Depends(get_current_admin)):
    """Removes an entire row (e.g. to fix a mistake before any seats in
    it are booked). Fails safe - refuses if any seat in the row is
    already Booked, to never silently delete a real booking's seat."""
    booked_check = (
        supabase_admin.table("event_seats")
        .select("id")
        .eq("event_id", event_id)
        .eq("seat_row", seat_row)
        .eq("status", "Booked")
        .execute()
    )
    if booked_check.data:
        raise HTTPException(status_code=400, detail="Cannot delete a row that has booked seats")

    supabase_admin.table("event_seats").delete().eq("event_id", event_id).eq("seat_row", seat_row).execute()
    return {"status": "deleted", "seat_row": seat_row}

# ---------- Coupons ----------

class CreateCouponRequest(BaseModel):
    code: str
    discount_type: str
    discount_value: float
    max_uses: int
    max_uses_per_user: int = 1
    valid_from: str | None = None
    valid_until: str | None = None
    event_id: str | None = None

@router.post("/coupons")
def create_coupon(payload: CreateCouponRequest, admin=Depends(get_current_admin)):
    data = payload.dict(exclude_none=True)
    data["code"] = data["code"].upper()
    try:
        supabase_admin.table("coupons").insert(data).execute()
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(status_code=400, detail="Coupon code already exists")
        raise HTTPException(status_code=500, detail=str(e))
    return {"message": "Coupon created successfully"}

@router.get("/coupons")
def list_coupons(admin=Depends(get_current_admin)):
    result = supabase_admin.table("coupons").select("*").order("created_at", desc=True).execute()
    return {"coupons": result.data}

class ToggleCouponRequest(BaseModel):
    is_active: bool

@router.patch("/coupons/{coupon_id}")
def toggle_coupon(coupon_id: str, payload: ToggleCouponRequest, admin=Depends(get_current_admin)):
    result = supabase_admin.table("coupons").update({"is_active": payload.is_active}).eq("id", coupon_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Coupon not found")
    return {"message": "Coupon status updated"}

# ---------- Admin Artist Management ----------

class UpdateArtistRequest(BaseModel):
    bio: Optional[str] = None
    image_url: Optional[str] = None
    social_links: Optional[Dict] = None

@router.get("/artists")
def admin_list_artists(admin=Depends(get_current_admin)):
    result = supabase_admin.table("artists").select("*").order("name").execute()
    return {"artists": result.data}

@router.patch("/artists/{artist_id}")
def update_artist(artist_id: str, payload: UpdateArtistRequest, admin=Depends(get_current_admin)):
    data = payload.dict(exclude_unset=True)
    if not data:
        return {"message": "No fields to update"}
        
    result = supabase_admin.table("artists").update(data).eq("artist_id", artist_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Artist not found")
    return {"message": "Artist updated", "artist": result.data[0]}

@router.post("/artists/{artist_id}/upload-image")
async def upload_artist_image(artist_id: str, image: UploadFile = File(...), admin=Depends(get_current_admin)):
    file_bytes = await image.read()
    safe_name = image.filename.replace(" ", "_")
    filename = f"artists/{int(time.time())}_{safe_name}"

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

        if isinstance(public_url_response, str):
            public_url = public_url_response
        elif isinstance(public_url_response, dict):
            public_url = public_url_response.get("publicURL") or public_url_response.get("publicUrl")
        else:
            public_url = str(public_url_response)

        # Update the artist profile
        supabase_admin.table("artists").update({"image_url": public_url}).eq("artist_id", artist_id).execute()
        return {"message": "Image uploaded successfully", "image_url": public_url}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {e}")

# ---------- Admin Venue Management ----------

class UpdateVenueRequest(BaseModel):
    address: Optional[str] = None
    capacity: Optional[int] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    image_url: Optional[str] = None

@router.get("/venues")
def admin_list_venues(admin=Depends(get_current_admin)):
    result = supabase_admin.table("venues").select("*").order("name").execute()
    return {"venues": result.data}

@router.patch("/venues/{venue_id}")
def update_venue(venue_id: str, payload: UpdateVenueRequest, admin=Depends(get_current_admin)):
    data = payload.dict(exclude_unset=True)
    if not data:
        return {"message": "No fields to update"}
        
    result = supabase_admin.table("venues").update(data).eq("venue_id", venue_id).execute()
    if not result.data:
        raise HTTPException(status_code=404, detail="Venue not found")
    return {"message": "Venue updated", "venue": result.data[0]}

@router.post("/venues/{venue_id}/upload-image")
async def upload_venue_image(venue_id: str, image: UploadFile = File(...), admin=Depends(get_current_admin)):
    file_bytes = await image.read()
    safe_name = image.filename.replace(" ", "_")
    filename = f"venues/{int(time.time())}_{safe_name}"

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

        if isinstance(public_url_response, str):
            public_url = public_url_response
        elif isinstance(public_url_response, dict):
            public_url = public_url_response.get("publicURL") or public_url_response.get("publicUrl")
        else:
            public_url = str(public_url_response)

        supabase_admin.table("venues").update({"image_url": public_url}).eq("venue_id", venue_id).execute()
        return {"message": "Image uploaded successfully", "image_url": public_url}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image upload failed: {e}")

# ---------- Pricing Notifications ----------

class ResolveNotificationRequest(BaseModel):
    action: str  # "approve" or "dismiss"
    final_price: Optional[int] = None

@router.get("/pricing-notifications")
def get_pricing_notifications(admin=Depends(get_current_admin)):
    admin_id = admin["user_id"]
    result = supabase_admin.table("pricing_notifications").select("*").eq("admin_user_id", admin_id).eq("status", "pending").order("created_at", desc=True).execute()
    return {"notifications": result.data}

@router.patch("/pricing-notifications/{notification_id}")
def resolve_pricing_notification(notification_id: str, payload: ResolveNotificationRequest, admin=Depends(get_current_admin)):
    admin_id = admin["user_id"]
    
    # 1. Fetch notification
    notif_res = supabase_admin.table("pricing_notifications").select("*").eq("id", notification_id).execute()
    if not notif_res.data:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    notif = notif_res.data[0]
    
    # 2. Verify ownership
    if notif["admin_user_id"] != admin_id:
        raise HTTPException(status_code=403, detail="Not authorized to resolve this notification")
        
    # 3. Verify status
    if notif["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Notification already {notif['status']}")
        
    # 4. Handle Dismiss
    if payload.action == "dismiss":
        upd = supabase_admin.table("pricing_notifications").update({
            "status": "dismissed",
            "acted_at": datetime.utcnow().isoformat()
        }).eq("id", notification_id).execute()
        return {"message": "Notification dismissed", "notification": upd.data[0]}
        
    # 5. Handle Approve
    if payload.action == "approve":
        if payload.final_price is None or payload.final_price <= 0:
            raise HTTPException(status_code=400, detail="Valid positive final_price required for approval")
            
        # Verify event/category
        cat_res = supabase_admin.table("ticket_categories").select("*").eq("event_id", notif["event_id"]).eq("category", notif["category"]).execute()
        if not cat_res.data:
            raise HTTPException(status_code=404, detail="Ticket category not found")
            
        # Update ticket price (only price_inr changes)
        supabase_admin.table("ticket_categories").update({
            "price_inr": payload.final_price
        }).eq("event_id", notif["event_id"]).eq("category", notif["category"]).execute()
        
        # Update notification
        upd = supabase_admin.table("pricing_notifications").update({
            "status": "approved",
            "final_price": payload.final_price,
            "acted_at": datetime.utcnow().isoformat()
        }).eq("id", notification_id).execute()
        
        return {"message": "Price updated successfully", "notification": upd.data[0]}
        
    raise HTTPException(status_code=400, detail="Invalid action")
