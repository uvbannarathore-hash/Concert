from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
import razorpay
import uuid
from datetime import datetime, timedelta, timezone
from app.supabase_client import supabase_admin
from app.routes.auth_routes import get_current_user
from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

router = APIRouter(prefix="/membership", tags=["membership"])
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

PLAN_PRICES = {"monthly": 149, "yearly": 1499}   # INR


class SubscribeRequest(BaseModel):
    plan_type: str = Field(..., pattern="^(monthly|yearly)$")


class VerifySubscribeRequest(BaseModel):
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str
    plan_type: str = Field(..., pattern="^(monthly|yearly)$")


@router.post("/subscribe")
def subscribe(payload: SubscribeRequest, current_user: dict = Depends(get_current_user)):
    """
    Creates a Razorpay order for a LiveWire Plus subscription.
    Open to all authenticated users — no organizer check.
    """
    amount_inr = PLAN_PRICES[payload.plan_type]
    amount_paise = amount_inr * 100
    receipt_id = f"plus_{uuid.uuid4().hex[:12]}"

    try:
        razorpay_order = razorpay_client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": receipt_id,
            "notes": {
                "user_id": current_user["user_id"],
                "plan_type": payload.plan_type,
                "type": "livewire_plus",
            }
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create Razorpay order: {str(e)}")

    return {
        "order_id": razorpay_order["id"],
        "amount": amount_inr,
        "plan_type": payload.plan_type,
        "razorpay_key_id": RAZORPAY_KEY_ID,  # public key, safe to expose
        "receipt": receipt_id,
    }


@router.post("/subscribe/verify")
def verify_subscribe(payload: VerifySubscribeRequest, current_user: dict = Depends(get_current_user)):
    """
    Verifies Razorpay signature and activates/extends LiveWire Plus.

    Renewal rule: EXTEND (add time to current expiry, not restart).
    A user renewing before expiry never loses remaining time — their
    billing period just gets longer. This is appropriate for a low-cost
    monthly plan where early renewal is a reward, not a trade-off.
    """
    try:
        razorpay_client.utility.verify_payment_signature({
            "razorpay_order_id": payload.razorpay_order_id,
            "razorpay_payment_id": payload.razorpay_payment_id,
            "razorpay_signature": payload.razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    now = datetime.now(timezone.utc)

    # EXTEND rule: if user has an active Plus plan, extend from current expiry.
    # If expired or never subscribed, start from now.
    user_res = supabase_admin.table("users").select(
        "is_plus_member, plus_expiry_date"
    ).eq("user_id", current_user["user_id"]).execute()

    base_date = now
    if user_res.data:
        row = user_res.data[0]
        if row.get("is_plus_member") and row.get("plus_expiry_date"):
            current_expiry = datetime.fromisoformat(row["plus_expiry_date"])
            if current_expiry.tzinfo is None:
                current_expiry = current_expiry.replace(tzinfo=timezone.utc)
            if current_expiry > now:
                base_date = current_expiry   # still active: add to the end

    if payload.plan_type == "monthly":
        new_expiry = base_date + timedelta(days=30)
    else:  # yearly
        new_expiry = base_date + timedelta(days=365)

    supabase_admin.table("users").update({
        "is_plus_member": True,
        "plus_plan_type": payload.plan_type,
        "plus_start_date": now.isoformat(),
        "plus_expiry_date": new_expiry.isoformat(),
    }).eq("user_id", current_user["user_id"]).execute()

    return {
        "message": "LiveWire Plus activated!",
        "plan_type": payload.plan_type,
        "expires_at": new_expiry.isoformat(),
    }


@router.get("/status")
def get_membership_status(current_user: dict = Depends(get_current_user)):
    """
    Returns the current user's Plus membership status and waiver usage
    for the current UTC calendar month.
    Used by the checkout page to show waiver slots remaining.
    """
    user_id = current_user["user_id"]
    now = datetime.now(timezone.utc)

    user_res = supabase_admin.table("users").select(
        "is_plus_member, plus_plan_type, plus_start_date, plus_expiry_date"
    ).eq("user_id", user_id).execute()

    if not user_res.data:
        return {"is_active": False, "waiver_slots_used": 0, "waiver_slots_total": 4}

    row = user_res.data[0]
    is_plus = row.get("is_plus_member", False)
    expiry_raw = row.get("plus_expiry_date")

    is_active = False
    if is_plus and expiry_raw:
        expiry = datetime.fromisoformat(expiry_raw)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        is_active = expiry >= now

    waiver_slots_used = 0
    if is_active:
        # Count waived bookings this calendar month (UTC).
        # Use fee_waived=true on booking_ledger, joined to non-cancelled bookings
        # for this user created within the current UTC month.
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

        # Get booking IDs for this user, this month, not cancelled
        bookings_res = supabase_admin.table("bookings").select("booking_id").eq(
            "user_id", user_id
        ).neq("status", "Cancelled").gte("created_at", month_start.isoformat()).execute()

        booking_ids = [b["booking_id"] for b in bookings_res.data]
        if booking_ids:
            waived_res = supabase_admin.table("booking_ledger").select("booking_id").eq(
                "fee_waived", True
            ).in_("booking_id", booking_ids).execute()
            waiver_slots_used = len(waived_res.data)

    return {
        "is_active": is_active,
        "plan_type": row.get("plus_plan_type"),
        "expires_at": row.get("plus_expiry_date"),
        "waiver_slots_used": waiver_slots_used,
        "waiver_slots_total": 4,
        "waiver_slots_remaining": max(0, 4 - waiver_slots_used) if is_active else 0,
    }
