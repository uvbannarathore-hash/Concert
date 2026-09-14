import time
import hmac
import hashlib
import logging
import razorpay
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from app.auth import get_current_user
from app.limiter import limiter
from app.supabase_client import supabase_admin
from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET, RAZORPAY_WEBHOOK_SECRET
from app.services.cancellation_service import (
    get_cancellation_eligibility,
    initiate_cancellation,
    _fetch_payment_and_refunds,
    _reconcile_refund_state,
)

logger = logging.getLogger("booking_routes")

router = APIRouter(prefix="/bookings", tags=["bookings"])

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


def _check_not_admin(current_user: dict):
    # current_user already carries is_admin from the get_current_user auth
    # dependency (it fetches the users row once to build this dict) - this
    # used to re-query the users table again here for the same value on
    # every booking-related request. Reusing the value already on hand
    # removes that redundant DB round-trip; the fail-safe behavior is
    # identical (get_current_user defaults is_admin to False if its own
    # profile fetch fails, so this stays just as safe as before).
    if current_user.get("is_admin"):
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
    coupon_code: str | None = None


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
    discount_amount = 0
    coupon_id = None

    if payload.coupon_code:
        coupon_res = supabase_admin.table("coupons").select("*").eq("code", payload.coupon_code.upper()).execute()
        if not coupon_res.data:
            raise HTTPException(status_code=400, detail="Invalid coupon code")
        coupon = coupon_res.data[0]
        
        if not coupon.get("is_active") or coupon.get("current_uses", 0) >= coupon.get("max_uses", 1):
            raise HTTPException(status_code=400, detail="Coupon is not valid or max uses reached")
        
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        if coupon.get("valid_from") and now < datetime.fromisoformat(coupon["valid_from"]):
            raise HTTPException(status_code=400, detail="Coupon not yet valid")
        if coupon.get("valid_until") and now > datetime.fromisoformat(coupon["valid_until"]):
            raise HTTPException(status_code=400, detail="Coupon expired")
        if coupon.get("event_id") and coupon["event_id"] != payload.event_id:
            raise HTTPException(status_code=400, detail="Coupon not valid for this event")
            
        if coupon["discount_type"] == "percentage":
            discount_amount = int(round(amount_inr * float(coupon["discount_value"]) / 100))
        elif coupon["discount_type"] == "fixed":
            discount_amount = int(round(float(coupon["discount_value"])))
            
        coupon_id = coupon["id"]

    final_amount_inr = amount_inr - discount_amount
    if final_amount_inr < 1:
        discount_amount = amount_inr - 1
        final_amount_inr = 1

    amount_paise = int(round(final_amount_inr * 100))  # Razorpay expects the smallest currency unit

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
    update_data = {"razorpay_order_id": razorpay_order["id"]}
    if coupon_id:
        update_data["coupon_id"] = coupon_id
        update_data["discount_amount"] = discount_amount
        update_data["total_amount"] = final_amount_inr
    else:
        update_data["discount_amount"] = 0
        update_data["total_amount"] = amount_inr

    supabase_admin.table("bookings").update(update_data).eq("booking_id", booking_id).execute()

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
    coupon_code: str | None = None


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

    amount_inr = float(data["total_price"])
    discount_amount = 0
    coupon_id = None

    if payload.coupon_code:
        coupon_res = supabase_admin.table("coupons").select("*").eq("code", payload.coupon_code.upper()).execute()
        if not coupon_res.data:
            # We already booked seats in DB, we should cancel booking before throwing
            supabase_admin.table("bookings").update({"status": "Cancelled", "payment_status": "Cancelled"}).eq("booking_id", data["booking_id"]).execute()
            raise HTTPException(status_code=400, detail="Invalid coupon code")
        coupon = coupon_res.data[0]
        
        if not coupon.get("is_active") or coupon.get("current_uses", 0) >= coupon.get("max_uses", 1):
            supabase_admin.table("bookings").update({"status": "Cancelled", "payment_status": "Cancelled"}).eq("booking_id", data["booking_id"]).execute()
            raise HTTPException(status_code=400, detail="Coupon is not valid or max uses reached")
        
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        if (coupon.get("valid_from") and now < datetime.fromisoformat(coupon["valid_from"])) or (coupon.get("valid_until") and now > datetime.fromisoformat(coupon["valid_until"])):
            supabase_admin.table("bookings").update({"status": "Cancelled", "payment_status": "Cancelled"}).eq("booking_id", data["booking_id"]).execute()
            raise HTTPException(status_code=400, detail="Coupon not valid at this time")
            
        if coupon.get("event_id") and coupon["event_id"] != payload.event_id:
            supabase_admin.table("bookings").update({"status": "Cancelled", "payment_status": "Cancelled"}).eq("booking_id", data["booking_id"]).execute()
            raise HTTPException(status_code=400, detail="Coupon not valid for this event")
            
        if coupon["discount_type"] == "percentage":
            discount_amount = int(round(amount_inr * float(coupon["discount_value"]) / 100))
        elif coupon["discount_type"] == "fixed":
            discount_amount = int(round(float(coupon["discount_value"])))
            
        coupon_id = coupon["id"]

    final_amount_inr = amount_inr - discount_amount
    if final_amount_inr < 1:
        discount_amount = amount_inr - 1
        final_amount_inr = 1

    amount_paise = int(round(final_amount_inr * 100))

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

    update_data = {"razorpay_order_id": razorpay_order["id"]}
    if coupon_id:
        update_data["coupon_id"] = coupon_id
        update_data["discount_amount"] = discount_amount
        update_data["total_amount"] = final_amount_inr
    else:
        update_data["discount_amount"] = 0
        update_data["total_amount"] = amount_inr

    supabase_admin.table("bookings").update(update_data).eq("booking_id", data["booking_id"]).execute()

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
        amount = booking_row.get("total_amount")
        if amount is None: # fallback for legacy bookings
            ticket_row = _get_ticket_or_404(booking_row["event_id"], booking_row["category"])
            amount = float(ticket_row["price_inr"]) * booking_row["seats_booked"]
            
        return {
            "message": "Booking confirmed",
            "booking_id": payload.booking_id,
            "payment_id": payload.razorpay_payment_id,
            "amount": amount,
        }

    # Idempotency guard: this booking was already cancelled (e.g. a prior
    # verify-payment attempt already found the coupon exhausted, refunded
    # the payment, and cancelled the booking below). Without this check, a
    # retry (network retry, double-tap, user reopening the tab) would fall
    # through, call consume_coupon again (fails again, same reason), and
    # call payment.refund() a second time on an amount Razorpay already
    # shows as refunded - the exact class of bug fixed in the cancellation
    # flow, just reachable from this endpoint too.
    if booking_row["status"] == "Cancelled":
        raise HTTPException(
            status_code=409,
            detail=f"This booking was already cancelled. Payment status: {booking_row.get('payment_status')}",
        )
        
    # Attempt to consume coupon atomically if one was used
    if booking_row.get("coupon_id"):
        try:
            supabase_admin.rpc(
                "consume_coupon",
                {
                    "p_booking_id": payload.booking_id,
                    "p_user_id": current_user["user_id"],
                    "p_coupon_id": booking_row["coupon_id"],
                },
            ).execute()
        except Exception as e:
            # Coupon consumption failed (e.g., concurrency limit reached).
            # Refund the payment and cancel the booking - reconciled
            # against Razorpay's actual refund state first (reusing the
            # same helpers cancellation_service.py uses) so this can never
            # call payment.refund() a second time on an amount already
            # refunded, even if this exact request is somehow retried
            # before the "Cancelled" guard above is written.
            logger.warning(f"consume_coupon failed for booking {payload.booking_id}: {e}")
            refund_covered = False
            try:
                payment_info, refunds_list = _fetch_payment_and_refunds(payload.razorpay_payment_id)
                captured_amount = payment_info.get("amount") or 0
                recon = _reconcile_refund_state(payment_info, refunds_list, captured_amount)
                if recon["actual_refunded_amount"] >= captured_amount:
                    # Already fully refunded (e.g. a concurrent request beat
                    # us here) - do NOT call payment.refund() again.
                    refund_covered = True
                elif recon["remaining_refundable_amount"] > 0:
                    razorpay_client.payment.refund(
                        payload.razorpay_payment_id,
                        {
                            "amount": recon["remaining_refundable_amount"],
                            "notes": {"booking_id": payload.booking_id, "reason": "coupon_exhausted"},
                        },
                    )
                    refund_covered = True
            except Exception as refund_err:
                logger.error(f"Refund reconciliation/attempt failed for booking {payload.booking_id}: {refund_err}")

            supabase_admin.table("bookings").update(
                {"status": "Cancelled", "payment_status": "Refunded" if refund_covered else "Refund Failed"}
            ).eq("booking_id", payload.booking_id).execute()
            raise HTTPException(status_code=409, detail="Coupon usage limit reached during checkout. Payment refunded.")

    supabase_admin.table("bookings").update(
        {
            "status": "Confirmed",
            "payment_status": "Paid",
            "razorpay_payment_id": payload.razorpay_payment_id,
        }
    ).eq("booking_id", payload.booking_id).execute()

    amount = booking_row.get("total_amount")
    if amount is None:
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

        # Check if this is a seat upgrade payment
        notes = entity.get("notes", {})
        upgrade_request_id = notes.get("upgrade_request_id")
        
        if upgrade_request_id:
            # Handle seat upgrade
            req_res = supabase_admin.table("seat_upgrade_requests").select("*").eq("id", upgrade_request_id).execute()
            if req_res.data:
                req = req_res.data[0]
                if req["status"] == "payment_pending":
                    # Verify mathematical amount match
                    booking_res = supabase_admin.table("bookings").select("*").eq("booking_id", req["original_booking_id"]).execute()
                    if booking_res.data:
                        booking_row = booking_res.data[0]
                        seats_booked = booking_row["seats_booked"]
                        
                        try:
                            # Re-fetch new category price
                            ticket_row = _get_ticket_or_404(req["event_id"], req["desired_category"])
                            new_total = float(ticket_row["price_inr"]) * seats_booked
                            
                            # Re-fetch old total
                            old_total = float(booking_row.get("total_amount") or 0)
                            if old_total == 0:
                                current_ticket_row = _get_ticket_or_404(req["event_id"], req["current_category"])
                                old_total = float(current_ticket_row["price_inr"]) * seats_booked
                            
                            price_diff = new_total - old_total
                            expected_amount_paise = int(round(price_diff * 100))
                            paid_amount_paise = payment_entity.get("amount", 0)
                            
                            if paid_amount_paise != expected_amount_paise:
                                logger.error(f"Seat upgrade webhook amount mismatch. Expected: {expected_amount_paise}, Paid: {paid_amount_paise}")
                                # Refund the invalid amount or handle manually later
                                return {"status": "ok"}
                                
                            # Atomic lock and finalize
                            supabase_admin.rpc("finalize_seat_upgrade", {
                                "p_request_id": upgrade_request_id,
                                "p_razorpay_payment_id": razorpay_payment_id,
                                "p_payment_amount": paid_amount_paise / 100.0
                            }).execute()
                            
                        except Exception as e:
                            logger.error(f"Failed to process seat upgrade webhook for request {upgrade_request_id}: {e}")
            return {"status": "ok"}

        # Original Booking Flow
        booking = (
            supabase_admin.table("bookings")
            .select("*")
            .eq("razorpay_payment_link_id", payment_link_id)
            .execute()
        )
        if booking.data:
            booking_row = booking.data[0]

            # Calculate amount (price * seats) – used for both payments and bookings total_amount
            ticket_row = _get_ticket_or_404(booking_row["event_id"], booking_row["category"])
            amount = float(ticket_row["price_inr"]) * booking_row["seats_booked"]

            # Update booking with payment details and persist total_amount. Use the same amount value as the
            # payments record so the two stay consistent. If total_amount is already set (e.g., duplicate webhook),
            # the same value will be written again – this is safe and idempotent.
            supabase_admin.table("bookings").update(
                {
                    "status": "Confirmed",
                    "payment_status": "Paid",
                    "razorpay_payment_id": razorpay_payment_id,
                    "total_amount": amount,
                }
            ).eq("booking_id", booking_row["booking_id"]).execute()

            # Idempotent insert into payments: only create a new row if this razorpay_payment_id hasn't been recorded yet.
            existing_payment = (
                supabase_admin.table("payments")
                .select("payment_id")
                .eq("payment_id", razorpay_payment_id)
                .execute()
            )
            if not existing_payment.data:
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


@router.get("/{booking_id}/payment-retry")
def get_payment_retry(booking_id: str, current_user: dict = Depends(get_current_user)):
    """Fetches original amount for payment retry flow."""
    booking = supabase_admin.table("bookings").select("*").eq("booking_id", booking_id).eq("user_id", current_user["user_id"]).execute()
    if not booking.data:
        raise HTTPException(status_code=404, detail="Booking not found")
    b = booking.data[0]
    if b["status"] != "Pending":
        raise HTTPException(status_code=400, detail="Only Pending bookings can be retried")
    ticket = _get_ticket_or_404(b["event_id"], b["category"])
    amount = int(round(float(ticket["price_inr"]) * b["seats_booked"] * 100))
    razorpay_order_id = b.get("razorpay_order_id")
    if not razorpay_order_id:
        razorpay_order = razorpay_client.order.create(
            {
                "amount": amount,
                "currency": "INR",
                "receipt": booking_id,
                "notes": {
                    "booking_id": booking_id,
                    "user_id": current_user["user_id"],
                    "event_id": b["event_id"],
                },
            }
        )
        razorpay_order_id = razorpay_order["id"]
        supabase_admin.table("bookings").update(
            {"razorpay_order_id": razorpay_order_id}
        ).eq("booking_id", booking_id).execute()

    return {"amount": amount, "currency": "INR", "razorpay_order_id": razorpay_order_id}


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
        .order("created_at", desc=True)
        .execute()
    )
    from app.config import RAZORPAY_KEY_ID
    return {"bookings": result.data, "razorpay_key_id": RAZORPAY_KEY_ID}


@router.get("/{booking_id}/cancellation-eligibility")
def check_cancellation_eligibility(booking_id: str, current_user: dict = Depends(get_current_user)):
    """
    Checks if a booking can be cancelled and calculates the expected refund.
    """
    eligibility = get_cancellation_eligibility(booking_id, current_user["user_id"])
    return eligibility


@router.post("/{booking_id}/cancel")
def cancel_booking(booking_id: str, current_user: dict = Depends(get_current_user)):
    """
    Cancels a booking. Filtered by BOTH booking_id and user_id so a
    user can only cancel their own booking.
    Automatically initiates a Razorpay refund if eligible.

    This is now a thin wrapper around cancellation_service.initiate_cancellation(),
    which owns the atomic claim / Razorpay refund-reconciliation / final-update
    flow. That function is the single source of truth for cancellation +
    refund logic - it's the same function the Chat and Voice agents call, so
    the amount-aware refund reconciliation (never re-refunding an amount
    Razorpay already shows as refunded) only has to live and be fixed in one
    place. Do not re-implement Razorpay refund calls here.
    """
    # Ownership check up front so we return 404 (not a generic failure) for
    # a booking that doesn't belong to this user, before doing any work.
    booking_check = (
        supabase_admin.table("bookings")
        .select("booking_id")
        .eq("booking_id", booking_id)
        .eq("user_id", current_user["user_id"])
        .execute()
    )
    if not booking_check.data:
        raise HTTPException(status_code=404, detail="Booking not found or it does not belong to this user.")

    result = initiate_cancellation(booking_id, current_user["user_id"])

    if not result.get("success"):
        message = result.get("message", "Unable to cancel booking.")
        # get_cancellation_eligibility() reasons all start with this prefix
        # (see initiate_cancellation) - treat those as a 400 (bad request /
        # not eligible), anything else (claim conflicts, DB races) as a 409.
        if message.startswith("Cannot cancel booking"):
            raise HTTPException(status_code=400, detail=message)
        raise HTTPException(status_code=409, detail=message)

    refund_details = result.get("refund_details") or {}
    return {
        "message": result.get("message", "Booking cancelled"),
        "booking_id": booking_id,
        "payment_status": result.get("payment_status"),
        "refund_status": result.get("refund_status") or refund_details.get("refund_status"),
        "refund_amount": result.get("refund_amount"),
        "refund_details": refund_details,
    }

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


@router.post("/{booking_id}/refund")
def initiate_refund(booking_id: str, current_user: dict = Depends(get_current_user)):
    """
    Internal/Admin manual refund endpoint. 
    Not used in the normal user flow since cancellation automatically refunds.
    """
    admin_check = current_user.get("is_admin")
    if not admin_check:
        raise HTTPException(status_code=403, detail="Only admins can initiate manual refunds.")

    result = (
        supabase_admin.table("bookings")
        .select("*")
        .eq("booking_id", booking_id)
        .execute()
    )
    if not result.data:
        raise HTTPException(status_code=404, detail="Booking not found")

    booking = result.data[0]
    
    if booking["payment_status"] in ["Refunded", "Refund Pending", "Refund Initiated", "Refund Processing"]:
        return {"message": f"Refund already processed or pending. Status: {booking['payment_status']}"}
    
    if not booking.get("razorpay_payment_id"):
        raise HTTPException(status_code=400, detail="No successful payment to refund")

    amount = booking.get("total_amount")
    if amount is None:
        # Check payments table for actual successful payment amount
        payment_check = supabase_admin.table("payments").select("amount").eq("booking_id", booking_id).eq("status", "Success").execute()
        if payment_check.data and payment_check.data[0].get("amount"):
            amount = payment_check.data[0]["amount"]
        else:
            ticket_row = _get_ticket_or_404(booking["event_id"], booking["category"])
            amount = float(ticket_row["price_inr"]) * booking["seats_booked"]
    
    amount_paise = int(round(float(amount) * 100))

    # Atomic claim: closes the TOCTOU window between the status check above
    # and the refund call below (e.g. two admins clicking "Refund" at the
    # same moment). Only one request can win this conditional update; the
    # other gets back no rows and is told a refund is already underway
    # instead of also calling Razorpay.
    claim = (
        supabase_admin.table("bookings")
        .update({"payment_status": "Refund Processing"})
        .eq("booking_id", booking_id)
        .not_.in_("payment_status", ["Refunded", "Refund Pending", "Refund Initiated", "Refund Processing"])
        .execute()
    )
    if not claim.data:
        refreshed = supabase_admin.table("bookings").select("payment_status").eq("booking_id", booking_id).execute()
        status_now = refreshed.data[0]["payment_status"] if refreshed.data else "unknown"
        return {"message": f"Refund already processed or pending. Status: {status_now}"}

    # Reconcile against Razorpay's actual refund state before calling
    # payment.refund() - reusing the same helpers cancellation_service.py
    # uses, rather than a third copy of this logic. This protects against
    # calling refund() again for an amount Razorpay already shows as
    # refunded (e.g. a previous attempt here or via the cancellation flow
    # succeeded but the DB write that would reflect it didn't land), and
    # against an ambiguous error (timeout) making a successful refund look
    # like a failure on retry.
    try:
        payment_info, refunds_list = _fetch_payment_and_refunds(booking["razorpay_payment_id"])
        captured_amount = payment_info.get("amount") or 0
        recon = _reconcile_refund_state(payment_info, refunds_list, amount_paise)

        if recon["actual_refunded_amount"] >= amount_paise and recon["matching_refund"] is not None:
            rzp_status = recon["matching_refund"].get("status")
        else:
            refund_amount = min(amount_paise - recon["actual_refunded_amount"], recon["remaining_refundable_amount"])
            if refund_amount <= 0:
                raise HTTPException(status_code=400, detail="Nothing left to refund on this payment.")
            try:
                refund = razorpay_client.payment.refund(booking["razorpay_payment_id"], {
                    "amount": refund_amount,
                    "notes": {"booking_id": booking_id, "reason": "admin_manual_refund"}
                })
                rzp_status = refund.get("status")
            except Exception as refund_err:
                # Ambiguous error - re-check before concluding it failed.
                payment_info2, refunds_list2 = _fetch_payment_and_refunds(booking["razorpay_payment_id"])
                recon2 = _reconcile_refund_state(payment_info2, refunds_list2, amount_paise)
                if recon2["matching_refund"] is not None and recon2["actual_refunded_amount"] > recon["actual_refunded_amount"]:
                    rzp_status = recon2["matching_refund"].get("status")
                else:
                    raise refund_err

        if rzp_status == "processed":
            db_payment_status = "Refunded"
        elif rzp_status == "pending":
            db_payment_status = "Refund Pending"
        else:
            db_payment_status = "Refund Initiated"
    except HTTPException:
        raise
    except Exception as e:
        supabase_admin.table("bookings").update(
            {"payment_status": "Refund Failed"}
        ).eq("booking_id", booking_id).execute()
        raise HTTPException(status_code=500, detail=f"Refund failed: {str(e)}")

    supabase_admin.table("bookings").update(
        {"payment_status": db_payment_status}
    ).eq("booking_id", booking_id).execute()

    return {"message": "Refund initiated successfully", "status": db_payment_status}