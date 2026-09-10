import time
import hmac
import hashlib
import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from app.auth import get_current_user
from app.limiter import limiter
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
    seats: int = Field(..., ge=1, le=20, description="Number of seats (1–20)")


@router.post("/create-order")
@limiter.limit("5/minute")
def create_order(request: Request, payload: CreateOrderRequest, current_user: dict = Depends(get_current_user)):
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

    # 1. Soft-check so we don't spam Razorpay if already sold out
    ticket_row = _get_ticket_or_404(payload.event_id, payload.category)
    if ticket_row["available_seats"] < payload.seats:
        raise HTTPException(status_code=409, detail="Not enough seats available")

    amount_inr = float(ticket_row["price_inr"]) * payload.seats
    amount_paise = int(round(amount_inr * 100))  # Razorpay expects the smallest currency unit

    booking_id = f"BK{int(time.time() * 1000)}"

    # 2. Create Razorpay order BEFORE locking seats (external APIs shouldn't block DB transactions)
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

    # 3. Atomically reserve seats AND create the Pending booking using the 5-arg RPC
    try:
        supabase_admin.rpc(
            "book_ticket_transaction",
            {
                "p_booking_id": booking_id,
                "p_user_id": current_user["user_id"],
                "p_event_id": payload.event_id,
                "p_category": payload.category,
                "p_seats_booked": payload.seats,
            },
        ).execute()
    except Exception as e:
        # DB threw an exception (e.g. 'Not enough seats available' or 'Ticket category not found')
        # The Razorpay order is orphaned, but costless. Safe to discard.
        raise HTTPException(status_code=409, detail=f"Could not secure seats: {str(e)}")

    # 4. Attach the Razorpay order ID to the successfully created booking
    supabase_admin.table("bookings").update(
        {"razorpay_order_id": razorpay_order["id"]}
    ).eq("booking_id", booking_id).execute()

    return {
        "booking_id": booking_id,
        "razorpay_order_id": razorpay_order["id"],
        "amount": amount_paise,
        "currency": "INR",
        "razorpay_key_id": RAZORPAY_KEY_ID,  # public key, safe to expose to frontend
    }


# ---------- Seat-map booking (events with a defined seat layout) ----------
# These endpoints power the interactive PVR/BookMyShow-style seat picker.
# For events without a seat layout (event_seats has zero rows for them),
# the frontend uses the plain quantity-based /create-order flow above
# instead - both flows write to the same bookings table and share the
# same verify-payment/razorpay-webhook/cancel endpoints below.

class LockSeatsRequest(BaseModel):
    event_id: str
    seat_ids: list[int] = Field(..., min_length=1, max_length=20)


@router.post("/lock-seats")
def lock_seats(payload: LockSeatsRequest, current_user: dict = Depends(get_current_user)):
    """
    Reserves specific seats for this user for 10 minutes while they check
    out - done atomically via the lock_seats RPC (SELECT ... FOR UPDATE
    SKIP LOCKED under the hood), so two people can never lock the same
    seat even if they click at the exact same moment. A background job
    (release_expired_seat_locks, on a 2-minute cron) frees any lock this
    old automatically if the user never completes payment.
    """
    _check_not_admin(current_user)

    if not payload.seat_ids:
        raise HTTPException(status_code=400, detail="No seats specified")

    result = supabase_admin.rpc(
        "lock_seats",
        {"p_event_id": payload.event_id, "p_seat_ids": payload.seat_ids, "p_user_id": current_user["user_id"]},
    ).execute()

    data = result.data
    if not data.get("success"):
        raise HTTPException(status_code=409, detail=data.get("message", "Could not lock seats"))
    return data


class ReleaseSeatsRequest(BaseModel):
    seat_ids: list[int]


@router.post("/release-seats")
def release_seats(payload: ReleaseSeatsRequest, current_user: dict = Depends(get_current_user)):
    """Lets a user give up their locked seats early (e.g. they changed
    their mind before paying), rather than waiting for the 10-minute
    expiry to free them up for other buyers."""
    supabase_admin.rpc(
        "release_locked_seats",
        {"p_seat_ids": payload.seat_ids, "p_user_id": current_user["user_id"]},
    ).execute()
    return {"status": "released"}


class CreateSeatOrderRequest(BaseModel):
    event_id: str
    seat_ids: list[int] = Field(..., min_length=1, max_length=20)


@router.post("/create-order-seats")
@limiter.limit("5/minute")
def create_order_seats(request: Request, payload: CreateSeatOrderRequest, current_user: dict = Depends(get_current_user)):
    """
    Seat-map equivalent of /create-order - converts this user's already-
    LOCKED seats (via /lock-seats) into a real Pending booking and a
    Razorpay Order, atomically via the book_specific_seats RPC. The
    seats must currently be locked to this exact user, or this fails -
    always call /lock-seats first.
    """
    _check_not_admin(current_user)

    result = supabase_admin.rpc(
        "book_specific_seats",
        {"p_user_id": current_user["user_id"], "p_event_id": payload.event_id, "p_seat_ids": payload.seat_ids},
    ).execute()

    data = result.data
    if not data.get("success"):
        raise HTTPException(status_code=409, detail=data.get("message", "Could not complete booking"))

    amount_paise = int(round(float(data["total_price"]) * 100))

    try:
        razorpay_order = razorpay_client.order.create(
            {
                "amount": amount_paise,
                "currency": "INR",
                "receipt": data["booking_id"],
                "notes": {
                    "booking_id": data["booking_id"],
                    "user_id": current_user["user_id"],
                    "event_id": payload.event_id,
                },
            }
        )
    except Exception as e:
        # Razorpay failed AFTER the DB already booked the seats.
        # Cancel immediately so trg_restore_specific_seats frees them.
        supabase_admin.table("bookings").update(
            {"status": "Cancelled", "payment_status": "Cancelled"}
        ).eq("booking_id", data["booking_id"]).execute()
        raise HTTPException(status_code=502, detail=f"Payment gateway error, seats released: {e}")

    supabase_admin.table("bookings").update(
        {"razorpay_order_id": razorpay_order["id"]}
    ).eq("booking_id", data["booking_id"]).execute()

    return {
        "booking_id": data["booking_id"],
        "razorpay_order_id": razorpay_order["id"],
        "amount": amount_paise,
        "currency": "INR",
        "razorpay_key_id": RAZORPAY_KEY_ID,
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

    # Idempotency guard: already confirmed (retry / webhook race) — return
    # success immediately so the frontend handler can set confirmedId/paymentId
    # and render the confirmation UI correctly without a second DB round-trip.
    if booking_row["status"] == "Confirmed":
        ticket_row = _get_ticket_or_404(booking_row["event_id"], booking_row["category"])
        amount = float(ticket_row["price_inr"]) * booking_row["seats_booked"]
        return {
            "message": "Booking confirmed",
            "booking_id": payload.booking_id,
            "payment_id": payload.razorpay_payment_id,
            "amount": amount,
        }

    supabase_admin.table("bookings").update(
        {
            "status": "Confirmed",
            "payment_status": "Paid",
            "razorpay_payment_id": payload.razorpay_payment_id,
        }
    ).eq("booking_id", payload.booking_id).execute()

    ticket_row = _get_ticket_or_404(booking_row["event_id"], booking_row["category"])
    amount = float(ticket_row["price_inr"]) * booking_row["seats_booked"]

    # Use upsert logic if table has a constraint, or just check existence
    existing_payment = supabase_admin.table("payments").select("*").eq("payment_id", payload.razorpay_payment_id).execute()
    if not existing_payment.data:
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

    if not RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

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
        .update({"status": "Cancelled", "payment_status": "Cancelled"})
        .eq("booking_id", booking_id)
        .eq("user_id", current_user["user_id"])
        .neq("status", "Cancelled")
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
        .select("booking_id, event_id, user_id, category, seats_booked, status, created_at, events(*)")
        .eq("booking_id", booking_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Digital ticket pass not found or invalid QR code")
    
    booking_data = result.data[0]
    
    # Manual lookup for user details (only name, NO PII like email/city to prevent scraping)
    user_result = supabase_admin.table("users").select("name").eq("user_id", booking_data["user_id"]).execute()
    user_info = user_result.data[0] if user_result.data else {"name": "Unknown"}
    
    return {"ticket": {**booking_data, "users": user_info}}