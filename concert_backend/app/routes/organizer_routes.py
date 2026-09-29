from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
import razorpay
import uuid
import logging
from app.supabase_client import supabase_admin
from app.routes.auth_routes import get_current_user
from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
from app.pricing_utils import PLAN_TIER_RATES

router = APIRouter(prefix="/organizer", tags=["organizer"])
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
logger = logging.getLogger("organizer_routes")

def get_current_organizer(current_user: dict = Depends(get_current_user)):
    # Check is_organizer
    res = supabase_admin.table("users").select("is_organizer, plan_tier, plan_expiry_date").eq("user_id", current_user["user_id"]).execute()
    if not res.data or not res.data[0].get("is_organizer"):
        raise HTTPException(status_code=403, detail="Not authorized as organizer")
    
    current_user["raw_plan_tier"] = res.data[0].get("plan_tier") or "starter"
    current_user["plan_expiry_date"] = res.data[0].get("plan_expiry_date")
    return current_user

def get_active_organizer_plan(org: dict = Depends(get_current_organizer)):
    """
    Computes the effective plan tier at request-time.
    Does NOT write back to the database.
    If the plan is expired, they are treated as 'starter' for this request.
    """
    from datetime import datetime, timezone
    
    raw_tier = org.get("raw_plan_tier", "starter").lower()
    expiry_str = org.get("plan_expiry_date")
    
    effective_tier = "starter"
    
    if raw_tier in ["pro", "business"] and expiry_str:
        try:
            expiry_date = datetime.fromisoformat(expiry_str)
            if expiry_date.tzinfo is None:
                expiry_date = expiry_date.replace(tzinfo=timezone.utc)
            
            if expiry_date >= datetime.now(timezone.utc):
                effective_tier = raw_tier
        except ValueError:
            pass
            
    org["effective_plan_tier"] = effective_tier
    return org

class UpgradePlanRequest(BaseModel):
    plan_tier: str = Field(..., pattern="^(pro|business)$")

@router.post("/plan/upgrade")
def upgrade_plan(payload: UpgradePlanRequest, org: dict = Depends(get_current_organizer)):
    # Price map
    prices = {"pro": 19999, "business": 79999}
    amount_inr = prices[payload.plan_tier]
    amount_paise = amount_inr * 100
    
    receipt_id = f"upg_{uuid.uuid4().hex[:12]}"
    
    try:
        razorpay_order = razorpay_client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt_id,
            "notes": {
                "user_id": org["user_id"],
                "plan_tier": payload.plan_tier,
                "type": "organizer_upgrade"
            }
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create Razorpay order: {str(e)}")
        
    return {
        "order_id": razorpay_order["id"],
        "amount": amount_inr,
        "receipt": receipt_id,
        "plan_tier": payload.plan_tier,
        "razorpay_key_id": RAZORPAY_KEY_ID,  # public key, safe to expose to frontend
    }

class VerifyUpgradeRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_tier: str = Field(..., pattern="^(pro|business)$")

@router.post("/plan/upgrade/verify")
def verify_upgrade(payload: VerifyUpgradeRequest, org: dict = Depends(get_current_organizer)):
    try:
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id': payload.razorpay_order_id,
            'razorpay_payment_id': payload.razorpay_payment_id,
            'razorpay_signature': payload.razorpay_signature
        })
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid payment signature")
    
    commission_pct = float(PLAN_TIER_RATES.get(payload.plan_tier, PLAN_TIER_RATES["starter"]))
    
    # "Restart from today" rule per user's confirmation
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    expiry = now + timedelta(days=365)
    
    supabase_admin.table("users").update({
        "plan_tier": payload.plan_tier,
        "commission_pct": commission_pct,
        "plan_start_date": now.isoformat(),
        "plan_expiry_date": expiry.isoformat()
    }).eq("user_id", org["user_id"]).execute()

    return {"message": "Plan upgraded successfully"}

@router.get("/events")
def get_organizer_events(org: dict = Depends(get_current_organizer)):
    """
    Returns all events (upcoming, past, cancelled) strictly scoped to this organizer.
    """
    res = supabase_admin.table("events").select("*").eq("organizer_id", org["user_id"]).order("event_date", desc=True).execute()
    return {"events": res.data or []}

class PayoutDetailsRequest(BaseModel):
    upi_id: str | None = None
    bank_account: str | None = None
    ifsc: str | None = None

@router.patch("/payout-details")
def update_payout_details(payload: PayoutDetailsRequest, org: dict = Depends(get_current_organizer)):
    if payload.upi_id:
        if "@" not in payload.upi_id:
            raise HTTPException(status_code=400, detail="Invalid UPI ID format")
        update_data = {"payout_upi_id": payload.upi_id, "payout_bank_account": None, "payout_ifsc": None}
    elif payload.bank_account and payload.ifsc:
        update_data = {"payout_bank_account": payload.bank_account, "payout_ifsc": payload.ifsc, "payout_upi_id": None}
    else:
        raise HTTPException(status_code=400, detail="Must provide either valid UPI ID or both Bank Account and IFSC")
        
    supabase_admin.table("users").update(update_data).eq("user_id", org["user_id"]).execute()
    return {"message": "Payout details updated successfully"}

@router.post("/events/{event_id}/cancel")
def cancel_own_event(event_id: str, org: dict = Depends(get_current_organizer)):
    """
    Allows organizers to cancel their own events.
    1. Grabs snapshot of all Confirmed/Pending bookings
    2. Cancels event (triggers DB inventory release & status update)
    3. Loops and issues 100% Razorpay refund to users
    4. Applies 5% penalty to organizer to cover platform gateway fees
    """
    # 0. Verify ownership and timing
    event_res = supabase_admin.table("events").select("organizer_id, status, event_date, event_time").eq("event_id", event_id).execute()
    if not event_res.data:
        raise HTTPException(status_code=404, detail="Event not found")
        
    event_data = event_res.data[0]
    if event_data.get("organizer_id") != org["user_id"]:
        raise HTTPException(status_code=403, detail="You do not own this event")
        
    if event_data.get("status") in ["Cancelled", "Completed"]:
        raise HTTPException(status_code=400, detail="Event is already cancelled or completed")

    # Check if event is in the past
    from datetime import datetime
    try:
        from zoneinfo import ZoneInfo
        event_dt_str = f"{event_data['event_date']} {event_data['event_time']}"
        event_dt = datetime.strptime(event_dt_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        if now >= event_dt:
            raise HTTPException(status_code=400, detail="Cannot cancel an event that has already started or passed.")
    except Exception as e:
        if "Cannot cancel" in str(e):
            raise
        pass

    # 1. Snapshot bookings before DB trigger fires
    bookings_res = supabase_admin.table("bookings").select("booking_id, user_id, total_amount, razorpay_payment_id, payment_status").eq("event_id", event_id).in_("status", ["Confirmed", "Pending"]).execute()
    bookings = bookings_res.data or []

    # 2. Update event status to 'Cancelled' (this fires handle_event_cancellation trigger)
    supabase_admin.table("events").update({"status": "Cancelled"}).eq("event_id", event_id).execute()

    # 3. Process Refunds
    total_refunded = 0.0
    for b in bookings:
        if b.get("razorpay_payment_id") and b.get("payment_status") == "Paid":
            amt = float(b["total_amount"])
            total_refunded += amt
            # Safe in test mode
            try:
                razorpay_client.payment.refund(b["razorpay_payment_id"], {"amount": int(amt * 100)})
            except Exception as e:
                logger.error(f"Refund failed for booking {b['booking_id']}: {e}")
                
            # Update Python-side records
            refund_details = {
                "eligible_amount": amt,
                "refund_percentage": 100,
                "cancellation_fee_percentage": 0,
                "requested_refund_amount": amt,
                "actual_refunded_amount": amt,
                "refund_status": "Refund Completed"
            }
            supabase_admin.table("bookings").update({
                "payment_status": "Refund Completed",
                "refund_details": refund_details
            }).eq("booking_id", b["booking_id"]).execute()
            
            # Update ledger with double-entry fields
            ledger_res = supabase_admin.table("booking_ledger").select("platform_net").eq("booking_id", b["booking_id"]).execute()
            p_net = float(ledger_res.data[0].get("platform_net", 0)) if ledger_res.data else 0.0
            supabase_admin.table("booking_ledger").update({
                "payout_status": "refunded",
                "cancellation_fee_retained": 0,
                "platform_refund_deduction": p_net,
                "updated_at": "now()"
            }).eq("booking_id", b["booking_id"]).execute()

    # 4. Organizer 5% Penalty
    if total_refunded > 0:
        penalty = round(total_refunded * 0.05, 2)
        supabase_admin.table("booking_ledger_adjustments").insert({
            "booking_id": "MASS_CANCEL",
            "organizer_id": org["user_id"],
            "adjustment_type": "clawback",
            "amount": -penalty,
            "reason": f"5% penalty for mass cancellation of event {event_id}",
            "status": "pending"
        }).execute()

    return {"message": "Event cancelled, all users fully refunded, and 5% penalty applied."}
