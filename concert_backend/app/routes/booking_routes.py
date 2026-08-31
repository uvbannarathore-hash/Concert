import time
import hmac
import hashlib
import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from app.auth import get_current_user
from app.supabase_client import supabase_admin
from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET

router = APIRouter(prefix="/bookings", tags=["bookings"])

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


def _check_not_admin(current_user: dict):
    admin_check = (
        supabase_admin.table("users")
        .select("is_admin")
        .eq("user_id", current_user["user_id"])
        .execute()
    )
    if admin_check.data and admin_check.data[0].get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="Admin accounts cannot book tickets. Please use a regular user account.",
        )


def _get_ticket_or_404(event_id: str, category: str):
    ticket = (
        supabase_admin.table("ticket_categories")
        .select("*")
        .eq("event_id", event_id)
        .eq("category", category)
        .execute()
    )
    if not ticket.data:
        raise HTTPException(status_code=404, detail="Ticket category not found for this event")
    return ticket.data[0]


class CreateOrderRequest(BaseModel):
    event_id: str
    category: str
    seats: int


@router.post("/create-order")
def create_order(payload: CreateOrderRequest, current_user: dict = Depends(get_current_user)):
    """
    PATH 1 - step 1 of 2 (website direct booking, Razorpay Checkout widget).

    1. Validates seats are available.
    2. Reserves the seats immediately (decrements available_seats) so two
       people can't both "hold" the last seat while paying.
    3. Creates a Razorpay Order.
    4. Inserts the booking as status='Pending', payment_status='Pending'.
    5. Returns everything the frontend needs to open Razorpay Checkout.

    If the user abandons payment, the booking stays 'Pending' until
    verify-payment is called (success) or it's cancelled (failure/timeout),
    which restores seats via the existing trg_restore_seats trigger.
    """
    _check_not_admin(current_user)

    ticket_row = _get_ticket_or_404(payload.event_id, payload.category)
    if ticket_row["available_seats"] < payload.seats:
        raise HTTPException(status_code=400, detail="Not enough seats available")

    amount_inr = float(ticket_row["price_inr"]) * payload.seats
    amount_paise = int(round(amount_inr * 100))  # Razorpay expects the smallest currency unit

    booking_id = f"BK{int(time.time() * 1000)}"

    razorpay_order = razorpay_client.order.create(
        {
            "amount": amount_paise,
            "currency": "INR",
            "receipt": booking_id,
            "notes": {
                "booking_id": booking_id,
                "user_id": current_user["user_id"],
                "event_id": payload.event_id,
            },
        }
    )

    # Reserve seats now so they can't be double-sold while this user pays
    supabase_admin.table("ticket_categories").update(
        {"available_seats": ticket_row["available_seats"] - payload.seats}
    ).eq("event_id", payload.event_id).eq("category", payload.category).execute()

    supabase_admin.table("bookings").insert(
        {
            "booking_id": booking_id,
            "user_id": current_user["user_id"],
            "event_id": payload.event_id,
            "category": payload.category,
            "seats_booked": payload.seats,
            "status": "Pending",
            "payment_status": "Pending",
            "razorpay_order_id": razorpay_order["id"],
        }
    ).execute()

    return {
        "booking_id": booking_id,
        "razorpay_order_id": razorpay_order["id"],
        "amount": amount_paise,
        "currency": "INR",
        "razorpay_key_id": RAZORPAY_KEY_ID,  # public key, safe to expose to frontend
    }


class VerifyPaymentRequest(BaseModel):
    booking_id: str
    razorpay_order_id: str
    razorpay_payment_id: str
    razorpay_signature: str


@router.post("/verify-payment")
def verify_payment(payload: VerifyPaymentRequest, current_user: dict = Depends(get_current_user)):
    """
    PATH 1 - step 2 of 2. Called by the frontend after Razorpay Checkout
    succeeds. Verifies the signature server-side (never trust the client)
    before marking the booking as Paid/Confirmed.
    """
    try:
        razorpay_client.utility.verify_payment_signature(
            {
                "razorpay_order_id": payload.razorpay_order_id,
                "razorpay_payment_id": payload.razorpay_payment_id,
                "razorpay_signature": payload.razorpay_signature,
            }
        )
    except razorpay.errors.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Payment signature verification failed")

    booking = (
        supabase_admin.table("bookings")
        .select("*")
        .eq("booking_id", payload.booking_id)
        .eq("user_id", current_user["user_id"])
        .eq("razorpay_order_id", payload.razorpay_order_id)
        .execute()
    )
    if not booking.data:
        raise HTTPException(status_code=404, detail="Booking not found for this order")

    booking_row = booking.data[0]

    supabase_admin.table("bookings").update(
        {
            "status": "Confirmed",
            "payment_status": "Paid",
            "razorpay_payment_id": payload.razorpay_payment_id,
        }
    ).eq("booking_id", payload.booking_id).execute()

    ticket_row = _get_ticket_or_404(booking_row["event_id"], booking_row["category"])
    amount = float(ticket_row["price_inr"]) * booking_row["seats_booked"]

    supabase_admin.table("payments").insert(
        {
            "payment_id": payload.razorpay_payment_id,
            "booking_id": payload.booking_id,
            "user_id": current_user["user_id"],
            "amount": amount,
            "method": "Razorpay",
            "status": "Success",
        }
    ).execute()

    return {
        "message": "Booking confirmed",
        "booking_id": payload.booking_id,
        "payment_id": payload.razorpay_payment_id,
        "amount": amount,
    }


@router.post("/razorpay-webhook")
async def razorpay_webhook(request: Request):
    """
    PATH 2 & 3 - Telegram bot and website AI chat both send a Razorpay
    Payment Link (created by the n8n book_ticket_transaction tool) instead
    of an embedded Checkout widget. When the user pays on Razorpay's
    hosted page, Razorpay calls this endpoint (no user/browser involved),
    so we identify the booking via razorpay_payment_link_id and confirm it
    here - the AI Agent never has to poll for payment status.

    Configure this URL in Razorpay Dashboard > Webhooks, with the same
    secret as RAZORPAY_WEBHOOK_SECRET, subscribed to 'payment_link.paid'.
    """
    body = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")

    expected_signature = hmac.new(
        RAZORPAY_WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    payload = await request.json()
    event = payload.get("event")

    if event == "payment_link.paid":
        entity = payload["payload"]["payment_link"]["entity"]
        payment_link_id = entity["id"]
        payment_entity = payload["payload"]["payment"]["entity"]
        razorpay_payment_id = payment_entity["id"]

        booking = (
            supabase_admin.table("bookings")
            .select("*")
            .eq("razorpay_payment_link_id", payment_link_id)
            .execute()
        )
        if booking.data:
            booking_row = booking.data[0]

            supabase_admin.table("bookings").update(
                {
                    "status": "Confirmed",
                    "payment_status": "Paid",
                    "razorpay_payment_id": razorpay_payment_id,
                }
            ).eq("booking_id", booking_row["booking_id"]).execute()

            ticket_row = _get_ticket_or_404(booking_row["event_id"], booking_row["category"])
            amount = float(ticket_row["price_inr"]) * booking_row["seats_booked"]

            supabase_admin.table("payments").insert(
                {
                    "payment_id": razorpay_payment_id,
                    "booking_id": booking_row["booking_id"],
                    "user_id": booking_row["user_id"],
                    "amount": amount,
                    "method": "Razorpay",
                    "status": "Success",
                }
            ).execute()

    # Always 200 on recognized calls so Razorpay doesn't keep retrying
    return {"status": "ok"}


@router.get("/me")
def my_bookings(current_user: dict = Depends(get_current_user)):
    """
    Returns the logged-in user's bookings. This is the same data the
    AI Agent's get_user_booking_history tool returns, but for direct
    frontend use (e.g. a 'My Bookings' page) rather than chat.
    """
    result = (
        supabase_admin.table("bookings")
        .select("*, events(*)")
        .eq("user_id", current_user["user_id"])
        .execute()
    )
    return {"bookings": result.data}


@router.post("/{booking_id}/cancel")
def cancel_booking(booking_id: str, current_user: dict = Depends(get_current_user)):
    """
    Cancels a booking. Filtered by BOTH booking_id and user_id so a
    user can only cancel their own booking - same security rule we
    applied inside the n8n cancel_booking tool.

    Seat restoration is handled automatically by the Postgres trigger
    (trg_restore_seats) - no extra logic needed here. This also doubles
    as the "release seats" path for abandoned/failed Razorpay payments
    on Pending bookings.
    """
    result = (
        supabase_admin.table("bookings")
        .update({"status": "Cancelled"})
        .eq("booking_id", booking_id)
        .eq("user_id", current_user["user_id"])
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="Booking not found, or it does not belong to this user",
        )

    return {"message": "Booking cancelled", "booking_id": booking_id}


@router.get("/{booking_id}/pass")
def get_booking_pass(booking_id: str):
    """
    Public digital pass validation endpoint for scanned QR codes.
    Returns the verified booking metadata, event schedule, venue coordinates,
    and seat details.
    """
    result = (
        supabase_admin.table("bookings")
        .select("booking_id, event_id, category, seats_booked, status, created_at, events(*), users(name, city, email)")
        .eq("booking_id", booking_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Digital ticket pass not found or invalid QR code")
    
    return {"ticket": result.data[0]}