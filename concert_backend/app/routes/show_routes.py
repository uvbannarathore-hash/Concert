"""
show_routes.py — "List Your Show" feature: lets any logged-in website user
submit their own event for admin review, and check the status of their
past submissions. Approval/rejection happens on the admin side (see the
show-submissions endpoints added to admin_routes.py) - this file only
covers the organizer-facing submit + view-own-history actions.
"""

import time
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, field_validator
from typing import Optional
from datetime import datetime
from app.auth import get_current_user
from app.supabase_client import supabase_admin

router = APIRouter(prefix="/shows", tags=["shows"])


class TicketCategoryIn(BaseModel):
    category: str
    price: float
    seats: int


class ShowSubmissionIn(BaseModel):
    artist_name: str
    venue_name: str
    city: str
    event_date: str  # YYYY-MM-DD
    event_time: str  # HH:MM
    event_type: str = "Concert"
    description: str | None = None
    categories: list[TicketCategoryIn]
    organizer_contact_name: str | None = None
    organizer_contact_phone: str | None = None
    organizer_notes: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    trailer_url: str | None = None

    @field_validator('trailer_url')
    @classmethod
    def validate_youtube_url(cls, v: str | None) -> str | None:
        if not v:
            return v
        import re
        pattern = r'(?:https?://)?(?:www\.|m\.)?(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([a-zA-Z0-9_-]{11})'
        if not re.search(pattern, v):
            raise ValueError("Invalid YouTube URL")
        return v


@router.post("/submit")
async def submit_show(
    payload: str = Form(...),  # JSON-encoded ShowSubmissionIn, since this is multipart (image upload)
    image: UploadFile = File(None),
    current_user: dict = Depends(get_current_user),
):
    """
    Submits a new event for admin review. Requires at least one ticket
    category. The event does NOT go live immediately - it's created here
    as a Pending row in show_submissions only, invisible to every public
    listing/search until an admin approves it (see admin_routes.py).

    Admin accounts are blocked from submitting, same as voice_db.py blocks
    admin accounts from booking tickets - admins already have direct
    event-creation power via the admin panel/AI assistant and don't need
    to go through a review queue for their own submissions.
    """
    if current_user.get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="Admin accounts cannot submit shows here - create the event directly from the admin panel.",
        )

    import json

    try:
        data = ShowSubmissionIn.model_validate_json(payload)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid submission data: {e}")

    if not data.categories:
        raise HTTPException(status_code=400, detail="At least one ticket category is required.")

    from datetime import datetime
    try:
        year = int(data.event_date.split("-")[0])
        current_year = datetime.now().year
        if not (current_year <= year <= current_year + 3):
            raise HTTPException(status_code=400, detail=f"Event year must be between {current_year} and {current_year + 3}.")
    except (ValueError, IndexError, AttributeError):
        raise HTTPException(status_code=400, detail="Invalid event_date format.")

    image_url = None
    if image is not None:
        file_bytes = await image.read()
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
            if isinstance(public_url_response, str):
                image_url = public_url_response
            elif isinstance(public_url_response, dict):
                image_url = public_url_response.get("publicURL") or public_url_response.get("publicUrl")
            else:
                image_url = str(public_url_response)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Image upload failed: {e}")

    result = (
        supabase_admin.table("show_submissions")
        .insert(
            {
                "submitted_by_user_id": current_user["user_id"],
                "artist_name": data.artist_name,
                "venue_name": data.venue_name,
                "city": data.city,
                "event_date": data.event_date,
                "event_time": data.event_time,
                "event_type": data.event_type,
                "description": data.description,
                "image_url": image_url,
                "latitude": data.latitude,
                "longitude": data.longitude,
                "categories": [c.model_dump() for c in data.categories],
                "organizer_contact_name": data.organizer_contact_name,
                "organizer_contact_phone": data.organizer_contact_phone,
                "organizer_notes": data.organizer_notes,
                "trailer_url": data.trailer_url,
                "status": "Pending",
            }
        )
        .execute()
    )

    if not result.data:
        raise HTTPException(status_code=500, detail="Could not save submission.")

    return {"message": "Show submitted for review", "submission": result.data[0]}


@router.get("/my-submissions")
async def my_submissions(current_user: dict = Depends(get_current_user)):
    """Returns the logged-in user's own submission history, newest first,
    so they can track whether each is Pending, Approved, or Rejected."""
    result = (
        supabase_admin.table("show_submissions")
        .select("*")
        .eq("submitted_by_user_id", current_user["user_id"])
        .order("created_at", desc=True)
        .execute()
    )
    return {"submissions": result.data}

class ResolveNotificationRequest(BaseModel):
    action: str  # "approve" or "dismiss"
    final_price: Optional[int] = None

@router.get("/pricing-notifications")
def get_organizer_pricing_notifications(current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    result = supabase_admin.table("pricing_notifications").select("*").eq("admin_user_id", user_id).eq("status", "pending").order("created_at", desc=True).execute()
    return {"notifications": result.data}

@router.patch("/pricing-notifications/{notification_id}")
def resolve_organizer_pricing_notification(notification_id: str, payload: ResolveNotificationRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    
    # 1. Fetch notification
    notif_res = supabase_admin.table("pricing_notifications").select("*").eq("id", notification_id).execute()
    if not notif_res.data:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    notif = notif_res.data[0]
    
    # 2. Verify ownership
    if notif["admin_user_id"] != user_id:
        raise HTTPException(status_code=403, detail="Not authorized to resolve this notification")
        
    # 3. Check status
    if notif["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Notification already {notif['status']}")
        
    # 4. Handle action
    if payload.action == "dismiss":
        upd = supabase_admin.table("pricing_notifications").update({
            "status": "dismissed",
            "resolved_at": datetime.now().isoformat()
        }).eq("id", notification_id).execute()
        return {"message": "Notification dismissed", "notification": upd.data[0]}
        
    elif payload.action == "approve":
        new_price = payload.final_price if payload.final_price else notif["suggested_price"]
        
        # Update ticket category price
        cat_res = supabase_admin.table("ticket_categories").select("*").eq("event_id", notif["event_id"]).eq("category", notif["category"]).execute()
        if not cat_res.data:
            raise HTTPException(status_code=404, detail="Ticket category not found")
            
        supabase_admin.table("ticket_categories").update({
            "price_inr": new_price
        }).eq("id", cat_res.data[0]["id"]).execute()
        
        # Update notification
        upd = supabase_admin.table("pricing_notifications").update({
            "status": "approved",
            "final_approved_price": new_price,
            "resolved_at": datetime.now().isoformat()
        }).eq("id", notification_id).execute()
        
        return {"message": "Price updated successfully", "notification": upd.data[0]}
        
    else:
        raise HTTPException(status_code=400, detail="Invalid action")