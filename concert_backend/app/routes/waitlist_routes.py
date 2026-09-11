from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.auth import get_current_user
from app.supabase_client import supabase_admin

router = APIRouter(prefix="/waitlist", tags=["waitlist"])

@router.post("/join/{event_id}")
def join_waitlist(event_id: str, current_user=Depends(get_current_user)):
    user_id = current_user["user_id"]
    
    # 1. Check if event exists and is Sold Out
    event_res = supabase_admin.table("events").select("status").eq("event_id", event_id).execute()
    if not event_res.data:
        raise HTTPException(status_code=404, detail="Event not found.")
        
    event_status = event_res.data[0].get("status")
    if event_status != "Sold Out":
        raise HTTPException(status_code=400, detail="Waitlist is only available for Sold Out events.")
        
    # 2. Check if already on waitlist
    existing = supabase_admin.table("waitlist").select("id").eq("event_id", event_id).eq("user_id", user_id).execute()
    if existing.data:
        raise HTTPException(status_code=400, detail="You are already on the waitlist for this event.")
        
    # 3. Insert
    insert_res = supabase_admin.table("waitlist").insert({
        "event_id": event_id,
        "user_id": user_id,
        "status": "Joined"
    }).execute()
    
    if not insert_res.data:
        raise HTTPException(status_code=500, detail="Failed to join waitlist.")
        
    return {"message": "Successfully joined the waitlist.", "data": insert_res.data[0]}

@router.get("/status/{event_id}")
def get_waitlist_status(event_id: str, current_user=Depends(get_current_user)):
    user_id = current_user["user_id"]
    
    res = supabase_admin.table("waitlist").select("id, status, created_at").eq("event_id", event_id).eq("user_id", user_id).execute()
    
    if res.data:
        return {"joined": True, "details": res.data[0]}
    else:
        return {"joined": False}

@router.delete("/leave/{event_id}")
def leave_waitlist(event_id: str, current_user=Depends(get_current_user)):
    user_id = current_user["user_id"]
    
    res = supabase_admin.table("waitlist").delete().eq("event_id", event_id).eq("user_id", user_id).execute()
    
    if not res.data:
        # Might not have been on the waitlist, which is fine
        return {"message": "You are not on the waitlist."}
        
    return {"message": "Successfully left the waitlist."}
