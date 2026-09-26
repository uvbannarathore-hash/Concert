from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
import razorpay
import uuid
from app.supabase_client import supabase_admin
from app.routes.auth_routes import get_current_user
from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
from app.pricing_utils import PLAN_TIER_RATES

router = APIRouter(prefix="/organizer", tags=["organizer"])
razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

def get_current_organizer(current_user: dict = Depends(get_current_user)):
    # Check is_organizer
    res = supabase_admin.table("users").select("is_organizer").eq("user_id", current_user["user_id"]).execute()
    if not res.data or not res.data[0].get("is_organizer"):
        raise HTTPException(status_code=403, detail="Not authorized as organizer")
    return current_user

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
