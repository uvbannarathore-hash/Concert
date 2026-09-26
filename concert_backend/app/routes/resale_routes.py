from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import datetime
import uuid
import logging
import razorpay
from app.auth import get_current_user
from app.supabase_client import supabase_admin
from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

logger = logging.getLogger(__name__)

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

router = APIRouter(prefix="/resale", tags=["resale"])

class ListTicketRequest(BaseModel):
    booking_id: str
    asking_price: float

class BuyResaleRequest(BaseModel):
    listing_id: str

@router.post("/create-order")
async def create_resale_order(payload: BuyResaleRequest, current_user: dict = Depends(get_current_user)):
    # This endpoint creates a Razorpay order but doesn't lock the ticket yet.
    # We don't want to lock on just intent since the listing could be held indefinitely.
    # The actual atomicity happens in the RPC when payment succeeds.
    buyer_id = current_user["user_id"]
    
    l_res = supabase_admin.table("ticket_resale_listings").select("asking_price, status").eq("id", payload.listing_id).execute()
    if not l_res.data:
        raise HTTPException(status_code=404, detail="Listing not found")
        
    listing = l_res.data[0]
    if listing["status"] != "Active":
        raise HTTPException(status_code=400, detail="Listing is no longer available")
        
    amount = float(listing["asking_price"])
    amount_paise = int(amount * 100)
    
    if amount_paise == 0:
        raise HTTPException(status_code=400, detail="Cannot create order for zero amount")
        
    try:
        order = razorpay_client.order.create({
            "amount": amount_paise,
            "currency": "INR",
            "receipt": f"receipt_{payload.listing_id[:10]}",
            "payment_capture": 1
        })
        
        new_booking_id = f"RES-{uuid.uuid4().hex[:8].upper()}"
        
        from app.config import RAZORPAY_KEY_ID
        return {
            "razorpay_order_id": order["id"],
            "razorpay_key_id": RAZORPAY_KEY_ID,
            "amount": amount,
            "currency": order["currency"],
            "booking_id": new_booking_id
        }
    except Exception as e:
        logger.error(f"Razorpay order creation failed: {e}")
        raise HTTPException(status_code=500, detail="Payment gateway error")

class VerifyResalePaymentRequest(BaseModel):
    listing_id: str
    booking_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str

@router.post("/list")
async def list_ticket(payload: ListTicketRequest, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    
    # 1. Verify booking exists, belongs to user, is Confirmed
    # And verify the seller has a payout method setup
    from app.services.payout_service import has_valid_payout_destination
    if not has_valid_payout_destination(user_id):
        raise HTTPException(status_code=400, detail="You must set up a Payout UPI ID or Bank Account in your Profile before listing a ticket.")

    if payload.booking_id.startswith("RES-"):
        raise HTTPException(status_code=400, detail="Resale tickets cannot be listed for resale again.")

    b_res = supabase_admin.table("bookings").select("total_amount, event_id, category, events(event_date)").eq("booking_id", payload.booking_id).eq("user_id", user_id).eq("status", "Confirmed").execute()
    
    if not b_res.data:
        raise HTTPException(status_code=400, detail="Invalid booking or booking not eligible for resale.")
        
    booking_data = b_res.data[0]
    original_total_paid = booking_data["total_amount"]
    event_id = booking_data["event_id"]
    category = booking_data["category"]
    
    event_date_str = booking_data.get("events", {}).get("event_date")
    if event_date_str:
        event_date = datetime.strptime(event_date_str, "%Y-%m-%d").date()
        if datetime.combine(event_date, datetime.min.time()) < datetime.now():
            raise HTTPException(status_code=400, detail="Cannot list tickets for past events.")

    # 2. Validate price <= 110%
    if original_total_paid is None:
        raise HTTPException(status_code=400, detail="Booking missing total_amount.")
        
    max_allowed = float(original_total_paid) * 1.10
    if payload.asking_price > max_allowed:
        raise HTTPException(status_code=400, detail=f"Asking price cannot exceed 110% of original price (Max: {max_allowed})")

    # 3. Check if already listed
    l_res = supabase_admin.table("ticket_resale_listings").select("id").eq("booking_id", payload.booking_id).eq("status", "Active").execute()
    if l_res.data:
        raise HTTPException(status_code=400, detail="Ticket is already listed for resale.")

    # 4. Insert listing
    insert_data = {
        "booking_id": payload.booking_id,
        "seller_id": user_id,
        "event_id": event_id,
        "category": category,
        "original_total_paid": original_total_paid,
        "asking_price": payload.asking_price,
        "status": "Active"
    }
    
    res = supabase_admin.table("ticket_resale_listings").insert(insert_data).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Failed to create listing.")
        
    return {"message": "Ticket listed for resale successfully", "listing_id": res.data[0]["id"]}


@router.get("/my-listings")
async def get_my_listings(current_user: dict = Depends(get_current_user)):
    res = supabase_admin.table("ticket_resale_listings").select("*").eq("seller_id", current_user["user_id"]).eq("status", "Active").execute()
    return {"results": res.data}

@router.get("/my-sold-tickets")
async def get_my_sold_tickets(current_user: dict = Depends(get_current_user)):
    # Pulls from resale_ledger to show completed sales and payout status
    res = supabase_admin.table("resale_ledger").select("*").eq("seller_id", current_user["user_id"]).order("created_at", desc=True).execute()
    return {"results": res.data}

@router.get("/events/{event_id}/tickets")
async def get_event_resale_tickets(event_id: str):
    res = supabase_admin.table("ticket_resale_listings").select("*").eq("event_id", event_id).eq("status", "Active").order("asking_price").execute()
    return {"results": res.data}


@router.post("/buy")
async def buy_resale_ticket(payload: VerifyResalePaymentRequest, current_user: dict = Depends(get_current_user)):
    buyer_id = current_user["user_id"]
    
    # We verify the payment signature just like regular bookings
    try:
        razorpay_client.utility.verify_payment_signature(
            {
                "razorpay_order_id": payload.razorpay_order_id,
                "razorpay_payment_id": payload.razorpay_payment_id,
                "razorpay_signature": payload.razorpay_signature,
            }
        )
    except Exception as e:
        logger.error(f"Signature verification failed: {e}")
        raise HTTPException(status_code=400, detail="Invalid payment signature")

    # Use an RPC for atomic locking and transfer
    try:
        rpc_res = supabase_admin.rpc(
            "buy_resale_ticket",
            {
                "p_listing_id": payload.listing_id,
                "p_buyer_id": buyer_id,
                "p_new_booking_id": payload.booking_id
            }
        ).execute()
        
        return {"message": "Successfully purchased resale ticket", "new_booking_id": payload.booking_id, "payment_id": payload.razorpay_payment_id}
    except Exception as e:
        logger.error(f"Error buying resale ticket: {str(e)}")
        
        # Idempotency check: If the RPC failed because the booking already exists 
        # (e.g. unique constraint violation on a retry), we should return success
        # instead of refunding.
        try:
            check_res = supabase_admin.table("resale_ledger").select("resale_booking_id").eq("resale_booking_id", payload.booking_id).execute()
            if check_res.data:
                logger.info(f"Idempotent hit: Resale purchase {payload.booking_id} already processed.")
                return {"message": "Successfully purchased resale ticket (already processed)", "new_booking_id": payload.booking_id, "payment_id": payload.razorpay_payment_id}
        except Exception as check_err:
            logger.error(f"Failed to verify idempotency: {check_err}")

        # Automatic refund: The payment succeeded, but the ticket could not be transferred
        # We rely on Razorpay's default full-refund behavior when no amount dictionary is provided.
        try:
            razorpay_client.payment.refund(payload.razorpay_payment_id)
            logger.info(f"Automatically fully refunded payment {payload.razorpay_payment_id} for failed resale purchase.")
        except Exception as refund_err:
            logger.error(f"Failed to auto-refund {payload.razorpay_payment_id}: {refund_err}")
            
        raise HTTPException(status_code=400, detail=f"Purchase failed, but payment was refunded. Reason: {str(e)}")


@router.post("/{listing_id}/cancel")
async def cancel_listing(listing_id: str, current_user: dict = Depends(get_current_user)):
    user_id = current_user["user_id"]
    
    res = supabase_admin.table("ticket_resale_listings").update({"status": "Cancelled"}).eq("id", listing_id).eq("seller_id", user_id).eq("status", "Active").execute()
    
    if not res.data:
        raise HTTPException(status_code=400, detail="Listing not found or already sold/cancelled.")
        
    return {"message": "Listing cancelled successfully"}
