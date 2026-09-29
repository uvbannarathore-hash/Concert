from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.supabase_client import supabase_admin
from app.auth import get_current_user_optional
from app.limiter import limiter

router = APIRouter(prefix="/insider", tags=["insider"])

class SubscribeRequest(BaseModel):
    email: EmailStr
    city: Optional[str] = None
    artist_id: Optional[str] = None

@router.post("/subscribe")
@limiter.limit("5/minute")
def subscribe_insider(request: Request, payload: SubscribeRequest, user: Optional[dict] = Depends(get_current_user_optional)):
    """
    Subscribes an email to the LiveWire Insider for specific alerts (city, artist, or general).
    Links to user_id if the user happens to be logged in.
    """
    # Normalize inputs
    email_normalized = payload.email.strip().lower()
    city_normalized = payload.city.strip().lower() if payload.city and payload.city.strip() else None
    artist_normalized = payload.artist_id.strip() if payload.artist_id and payload.artist_id.strip() else None
    user_id = user["user_id"] if user else None
    
    try:
        # Atomic upsert to avoid race conditions (TOCTOU flaw)
        supabase_admin.table("insider_subscriptions").upsert(
            {
                "email": email_normalized,
                "city": city_normalized,
                "artist_id": artist_normalized,
                "user_id": user_id,
                "is_active": True,
                "updated_at": "now()"
            },
            on_conflict="email,city,artist_id"
        ).execute()
        return {"message": "Successfully joined the LiveWire Insider list!"}
    except Exception as e:
        import logging
        logging.error(f"Subscription error for {email_normalized}: {e}")
        # Return generic error to prevent leaking DB structure/constraint errors
        raise HTTPException(status_code=500, detail="Failed to subscribe. Please try again later.")

class UnsubscribeRequest(BaseModel):
    unsubscribe_token: str

def _deactivate_subscription(token: str) -> None:
    """Helper to deactivate a subscription by its unique token."""
    try:
        res = supabase_admin.table("insider_subscriptions").update({
            "is_active": False,
            "updated_at": "now()"
        }).eq("unsubscribe_token", token).execute()
        
        if not res.data:
            raise HTTPException(status_code=404, detail="Invalid unsubscribe token.")
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logging.error(f"Unsubscribe error with token {token}: {e}")
        raise HTTPException(status_code=500, detail="Failed to unsubscribe. Please try again later.")

@router.get("/unsubscribe", response_class=HTMLResponse)
@limiter.limit("10/minute")
def unsubscribe_insider_get(request: Request, token: str):
    """
    Handles GET requests directly from email footer links.
    """
    _deactivate_subscription(token)
    return "<html><body><h2>You've been successfully unsubscribed.</h2><p>You will no longer receive this LiveWire Insider alert.</p></body></html>"

@router.post("/unsubscribe")
@limiter.limit("10/minute")
def unsubscribe_insider_post(request: Request, payload: UnsubscribeRequest):
    """
    Securely deactivates an insider subscription using a cryptographically random token.
    (Used by in-app settings or other programmatic clients).
    """
    _deactivate_subscription(payload.unsubscribe_token)
    return {"message": "Successfully unsubscribed from this LiveWire Insider alert."}
