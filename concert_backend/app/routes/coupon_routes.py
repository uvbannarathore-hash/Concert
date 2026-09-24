from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app.supabase_client import supabase_admin
from app.auth import get_current_user
from datetime import datetime, timezone
import math

router = APIRouter(prefix="/coupons", tags=["coupons"])

class ValidateCouponRequest(BaseModel):
    code: str
    event_id: str
    category: str
    seats: int

def get_current_utc():
    return datetime.now(timezone.utc)

@router.post("/validate")
def validate_coupon(payload: ValidateCouponRequest, current_user: dict = Depends(get_current_user)):
    # 1. Fetch the ticket price securely from the backend
    ticket_category = supabase_admin.table("ticket_categories").select("price_inr").eq("event_id", payload.event_id).eq("category", payload.category).execute()
    if not ticket_category.data:
        raise HTTPException(status_code=400, detail="Invalid event or category")
    
    price_inr = float(ticket_category.data[0]["price_inr"])
    original_amount = int(round(price_inr * payload.seats))
    
    # 2. Fetch the coupon
    coupon_data = supabase_admin.table("coupons").select("*").eq("code", payload.code.upper()).execute()
    if not coupon_data.data:
        raise HTTPException(status_code=400, detail="Invalid coupon code")
    
    coupon = coupon_data.data[0]
    
    # 3. Validation logic
    if not coupon.get("is_active"):
        raise HTTPException(status_code=400, detail="This coupon is no longer active")
        
    if coupon.get("current_uses", 0) >= coupon.get("max_uses", 1):
        raise HTTPException(status_code=400, detail="This coupon has reached its maximum usage limit")
        
    now = get_current_utc()
    
    if coupon.get("valid_from"):
        valid_from = datetime.fromisoformat(coupon["valid_from"])
        if now < valid_from:
            raise HTTPException(status_code=400, detail="This coupon is not yet valid")
            
    if coupon.get("valid_until"):
        valid_until = datetime.fromisoformat(coupon["valid_until"])
        if now > valid_until:
            raise HTTPException(status_code=400, detail="This coupon has expired")
            
    if coupon.get("event_id") and coupon["event_id"] != payload.event_id:
        raise HTTPException(status_code=400, detail="This coupon is not valid for this event")
        
    if coupon.get("owner_user_id") and coupon["owner_user_id"] != current_user["user_id"]:
        raise HTTPException(status_code=400, detail="This coupon is not valid for this user")
        
    # 4. Calculate discount
    discount_value = float(coupon["discount_value"])
    if coupon["discount_type"] == "percentage":
        discount_amount = int(round(original_amount * (discount_value / 100)))
    elif coupon["discount_type"] == "fixed":
        discount_amount = int(round(discount_value))
    else:
        raise HTTPException(status_code=400, detail="Invalid discount type")
        
    # 5. Cap discount (Minimum payable amount is ₹1)
    final_amount = original_amount - discount_amount
    if final_amount < 1:
        discount_amount = original_amount - 1
        final_amount = 1
        
    return {
        "valid": True,
        "coupon_id": coupon["id"],
        "code": coupon["code"],
        "original_amount": original_amount,
        "discount_amount": discount_amount,
        "final_amount": final_amount,
        "message": "Coupon applied successfully"
    }
