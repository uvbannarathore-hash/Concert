from fastapi import APIRouter, Depends, HTTPException
from app.supabase_client import supabase_admin
from app.auth import get_current_user

router = APIRouter(prefix="/payouts", tags=["payouts"])

@router.get("/pending")
def get_pending_payouts(current_user: dict = Depends(get_current_user)):
    """
    Shows the organizer their total accrued balances:
    - total pending payout
    - total clawbacks
    - net payable
    """
    user_id = current_user["user_id"]
    
    # Check if payout destination is missing
    from app.services.payout_service import has_valid_payout_destination
    payout_missing = not has_valid_payout_destination(user_id)

    # Verify the user is an organizer (or has events)
    events_res = supabase_admin.table("events").select("event_id, event_date").eq("organizer_id", user_id).execute()
    if not events_res.data:
        return {
            "total_pending_payout": 0.0,
            "total_clawbacks": 0.0,
            "net_payable": 0.0
        }
        
    event_ids = [e["event_id"] for e in events_res.data]
    # Filter out events that haven't happened yet to avoid paying out
    # before the cancellation window completely closes.
    from datetime import datetime, timezone
    now_utc = datetime.now(timezone.utc)
    
    # 1. Total pending payout from booking_ledger
    # payout_status = 'pending' means the booking was paid and the organizer is owed money.
    # We only include events that have passed (date < today).
    valid_event_ids = []
    for e in events_res.data:
        try:
            # simple check: if event_date is earlier than today, it's eligible
            event_dt = datetime.fromisoformat(e["event_date"]).replace(tzinfo=timezone.utc)
            if event_dt < now_utc:
                valid_event_ids.append(e["event_id"])
        except Exception:
            # If date format is weird, fallback to include it or skip it? Let's skip to be safe.
            pass
            
    bookings_res = supabase_admin.table("bookings") \
        .select("booking_id") \
        .in_("event_id", valid_event_ids) \
        .execute()
        
    booking_ids = [b["booking_id"] for b in bookings_res.data]
    
    total_pending_payout = 0.0
    if booking_ids:
        # fetch pending ledger entries
        # PostgREST limit might be an issue if there are thousands, but we'll assume it's fine for now or chunk it.
        # Let's chunk if large, or just use an RPC if available. Since we don't have an RPC, we will fetch.
        # Actually, booking_ledger_adjustments has organizer_id. 
        # For booking_ledger, it doesn't have organizer_id, only booking_id.
        ledger_res = supabase_admin.table("booking_ledger") \
            .select("organizer_payout") \
            .eq("payout_status", "pending") \
            .in_("booking_id", booking_ids) \
            .execute()
            
        for row in ledger_res.data:
            total_pending_payout += float(row["organizer_payout"])
            
    # 2. Total clawbacks from booking_ledger_adjustments
    adjustments_res = supabase_admin.table("booking_ledger_adjustments") \
        .select("amount") \
        .eq("organizer_id", user_id) \
        .eq("status", "pending") \
        .execute()
        
    total_clawbacks = 0.0
    for row in adjustments_res.data:
        # amounts are negative
        total_clawbacks += float(row["amount"])
        
    net_payable = total_pending_payout + total_clawbacks # since clawbacks are negative
    
    if payout_missing and net_payable > 0:
        net_payable = 0.0
    
    return {
        "total_pending_payout": total_pending_payout,
        "total_clawbacks": total_clawbacks,
        "net_payable": net_payable,
        "payout_destination_missing": payout_missing
    }
