from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth import get_current_user
from app.supabase_client import supabase_admin

router = APIRouter(prefix="/wishlist", tags=["wishlist"])


class WishlistRequest(BaseModel):
    event_id: str


@router.get("")
def get_wishlist(current_user: dict = Depends(get_current_user)):
    """
    Returns the logged-in user's wishlisted events, joined with event details
    so the frontend doesn't need a second round trip.
    """
    result = (
        supabase_admin.table("wishlist")
        .select("event_id, added_at")
        .eq("user_id", current_user["user_id"])
        .order("added_at", desc=True)
        .execute()
    )

    if not result.data:
        return {"wishlist": []}

    event_ids = [row["event_id"] for row in result.data]
    events = (
        supabase_admin.table("events")
        .select("*")
        .in_("event_id", event_ids)
        .execute()
    )

    event_map = {e["event_id"]: e for e in events.data}
    ordered = [event_map[eid] for eid in event_ids if eid in event_map]

    return {"wishlist": ordered}


@router.post("")
def add_to_wishlist(payload: WishlistRequest, current_user: dict = Depends(get_current_user)):
    try:
        supabase_admin.table("wishlist").insert(
            {"user_id": current_user["user_id"], "event_id": payload.event_id}
        ).execute()
    except Exception:
        # Likely a duplicate (already wishlisted) - not an error the user needs to see
        pass
    return {"message": "Added to wishlist"}


@router.delete("/{event_id}")
def remove_from_wishlist(event_id: str, current_user: dict = Depends(get_current_user)):
    result = (
        supabase_admin.table("wishlist")
        .delete()
        .eq("user_id", current_user["user_id"])
        .eq("event_id", event_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Not in wishlist")
    return {"message": "Removed from wishlist"}
