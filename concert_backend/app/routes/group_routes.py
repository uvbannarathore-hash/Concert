from fastapi import APIRouter, HTTPException, Request, Depends
from pydantic import BaseModel
from datetime import datetime, timezone
from app.supabase_client import supabase_admin
from app.auth import get_current_user

router = APIRouter(prefix="/group-invite", tags=["group_invites"])
session_router = APIRouter(prefix="/group-bookings", tags=["group_bookings"])

def _check_session_expiry(session_row):
    expires_at_str = session_row.get("expires_at")
    if not expires_at_str:
        return False
        
    try:
        # expires_at from postgres is usually ISO 8601 string
        expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires_at:
            # Mark expired
            if session_row["status"] == "collecting_responses":
                supabase_admin.table("group_booking_sessions").update(
                    {"status": "expired"}
                ).eq("id", session_row["id"]).execute()
                session_row["status"] = "expired"
            return True
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Error parsing expires_at: {e}")
    return False

@router.get("/{invite_id}")
def get_invite_details(invite_id: str):
    """Public endpoint for friends to view their invite details."""
    invite_res = supabase_admin.table("group_booking_invites").select("*, group_booking_sessions(*)").eq("id", invite_id).execute()
    if not invite_res.data:
        raise HTTPException(status_code=404, detail="Invite not found")
        
    invite = invite_res.data[0]
    session = invite.get("group_booking_sessions")
    if not session:
        raise HTTPException(status_code=404, detail="Group session not found")
        
    # Check expiry
    _check_session_expiry(session)
        
    # Get event details
    event_res = supabase_admin.table("events").select("event_name:artist_name, event_date, event_time, venue_name, city").eq("event_id", session["event_id"]).execute()
    event = event_res.data[0] if event_res.data else {}
    
    # Get initiator name
    user_res = supabase_admin.table("users").select("name").eq("user_id", session["initiator_user_id"]).execute()
    initiator_name = user_res.data[0].get("name", "A friend") if user_res.data else "A friend"
    
    return {
        "invite_id": invite["id"],
        "status": invite["status"],
        "friend_email": invite["friend_email"],
        "initiator_name": initiator_name,
        "session_status": session["status"],
        "event_name": event.get("event_name"),
        "event_date": event.get("event_date"),
        "event_time": event.get("event_time"),
        "venue_name": event.get("venue_name"),
        "city": event.get("city"),
        "category": session["category"],
        "total_seats": session["total_seats"],
        "expires_at": session["expires_at"]
    }

def _notify_initiator(session_id: str, message: str):
    from app.services.email_service import send_generic_notification
    
    session_res = supabase_admin.table("group_booking_sessions").select("initiator_user_id").eq("id", session_id).execute()
    if not session_res.data:
        return
        
    initiator_id = session_res.data[0]["initiator_user_id"]
    user_res = supabase_admin.table("users").select("email, telegram_chat_id, notify_telegram_for_website").eq("user_id", initiator_id).execute()
    
    if user_res.data:
        user = user_res.data[0]
        telegram_chat_id = user.get("telegram_chat_id") if user.get("notify_telegram_for_website") else None
        email = user.get("email")
        
        send_generic_notification(
            email=email,
            telegram_chat_id=telegram_chat_id,
            subject="LiveWire Group Booking Update",
            message=message
        )

@router.post("/{invite_id}/accept")
def accept_invite(invite_id: str):
    invite_res = supabase_admin.table("group_booking_invites").select("*, group_booking_sessions(*)").eq("id", invite_id).execute()
    if not invite_res.data:
        raise HTTPException(status_code=404, detail="Invite not found")
        
    invite = invite_res.data[0]
    session = invite.get("group_booking_sessions")
    
    # Check expiry
    if _check_session_expiry(session) or session["status"] == "expired":
        raise HTTPException(status_code=400, detail="This group booking session has expired.")
        
    if session["status"] not in ["collecting_responses"]:
        raise HTTPException(status_code=400, detail=f"Cannot accept invite. Session is currently: {session['status']}")
        
    if invite["status"] == "accepted":
        return {"status": "success", "message": "Already accepted."}
        
    # Update invite
    now = datetime.now(timezone.utc).isoformat()
    supabase_admin.table("group_booking_invites").update({
        "status": "accepted",
        "responded_at": now
    }).eq("id", invite_id).execute()
    
    # Check if all invites are accepted
    all_invites = supabase_admin.table("group_booking_invites").select("status").eq("group_session_id", session["id"]).execute()
    pending = [i for i in all_invites.data if i["status"] != "accepted" and i["id"] != invite_id]
    
    if not pending:
        # All accepted, mark ready!
        supabase_admin.table("group_booking_sessions").update({
            "status": "ready"
        }).eq("id", session["id"]).execute()
        
        # Notify initiator safely
        try:
            _notify_initiator(session["id"], "🎉 Your group booking is READY! Everyone has accepted. Ask the Customer Agent to finalize your booking to complete the payment.")
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Notification failed after successful RSVP: {e}")
            return {"status": "success", "message": "Invite accepted. (Note: Failed to notify the initiator)"}
            
    return {"status": "success", "message": "Invite accepted."}

@router.post("/{invite_id}/decline")
def decline_invite(invite_id: str):
    invite_res = supabase_admin.table("group_booking_invites").select("*, group_booking_sessions(*)").eq("id", invite_id).execute()
    if not invite_res.data:
        raise HTTPException(status_code=404, detail="Invite not found")
        
    invite = invite_res.data[0]
    session = invite.get("group_booking_sessions")
    
    if session["status"] not in ["collecting_responses", "ready"]:
        raise HTTPException(status_code=400, detail=f"Cannot decline. Session is: {session['status']}")
        
    if invite["status"] == "declined":
        return {"status": "success", "message": "Already declined."}
        
    now = datetime.now(timezone.utc).isoformat()
    supabase_admin.table("group_booking_invites").update({
        "status": "declined",
        "responded_at": now
    }).eq("id", invite_id).execute()
    
    # If the session was 'ready', it needs to fall back to 'collecting_responses'
    if session["status"] == "ready":
        supabase_admin.table("group_booking_sessions").update({
            "status": "collecting_responses"
        }).eq("id", session["id"]).execute()
    
    # Notify initiator safely
    try:
        _notify_initiator(session["id"], f"⚠️ Note: {invite.get('friend_email')} has declined the group booking invitation. You can cancel the booking or invite someone else.")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Notification failed after successful RSVP decline: {e}")
        return {"status": "success", "message": "Invite declined. (Note: Failed to notify the initiator)"}
    
    return {"status": "success", "message": "Invite declined."}

@session_router.get("/{session_id}")
def get_session_status(session_id: str, current_user: dict = Depends(get_current_user)):
    session_res = supabase_admin.table("group_booking_sessions").select("*").eq("id", session_id).eq("initiator_user_id", current_user["user_id"]).execute()
    if not session_res.data:
        raise HTTPException(status_code=404, detail="Group booking session not found")
        
    session = session_res.data[0]
    _check_session_expiry(session)
    
    invites_res = supabase_admin.table("group_booking_invites").select("*").eq("group_session_id", session_id).execute()
    
    return {
        "session": session,
        "invites": invites_res.data
    }
