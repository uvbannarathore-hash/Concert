"""
show_routes.py — "List Your Show" feature: lets any logged-in website user
submit their own event for admin review, and check the status of their
past submissions. Approval/rejection happens on the admin side (see the
show-submissions endpoints added to admin_routes.py) - this file only
covers the organizer-facing submit + view-own-history actions.
"""

import time
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
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
    categories: list[TicketCategoryIn]
    organizer_contact_name: str | None = None
    organizer_contact_phone: str | None = None
    organizer_notes: str | None = None
    latitude: float | None = None
    longitude: float | None = None


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
                "image_url": image_url,
                "latitude": data.latitude,
                "longitude": data.longitude,
                "categories": [c.model_dump() for c in data.categories],
                "organizer_contact_name": data.organizer_contact_name,
                "organizer_contact_phone": data.organizer_contact_phone,
                "organizer_notes": data.organizer_notes,
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