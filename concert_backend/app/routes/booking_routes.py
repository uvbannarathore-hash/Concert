import time
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth import get_current_user
from app.supabase_client import supabase_admin

router = APIRouter(prefix="/bookings", tags=["bookings"])


class CreateBookingRequest(BaseModel):
    event_id: str
    category: str
    seats: int
    payment_method: str = "Card"  # 'Card', 'UPI', 'Wallet' - dummy, not verified


@router.post("")
def create_booking(payload: CreateBookingRequest, current_user: dict = Depends(get_current_user)):
    """
    Creates a booking directly against Supabase (bypasses n8n/AI Agent
    for speed - booking writes should be fast and transactional).

    Steps:
    1. Check seat availability for the requested category.
    2. Insert the booking row (linked to the REAL user_id).
    3. Decrement available_seats.
    4. Record a dummy payment (no real gateway - this is a simulated
       transaction so the flow feels complete end-to-end).

    NOTE: For true race-condition safety (two users booking the last
    seat at the same time), this logic should eventually move into a
    Postgres function/RPC that does the check-and-decrement atomically.
    This version is fine for learning/testing.
    """
    ticket = (
        supabase_admin.table("ticket_categories")
        .select("*")
        .eq("event_id", payload.event_id)
        .eq("category", payload.category)
        .execute()
    )

    if not ticket.data:
        raise HTTPException(status_code=404, detail="Ticket category not found for this event")

    ticket_row = ticket.data[0]
    if ticket_row["available_seats"] < payload.seats:
        raise HTTPException(status_code=400, detail="Not enough seats available")

    booking_id = f"BK{int(time.time() * 1000)}"
    amount = float(ticket_row["price_inr"]) * payload.seats

    supabase_admin.table("bookings").insert(
        {
            "booking_id": booking_id,
            "user_id": current_user["user_id"],
            "event_id": payload.event_id,
            "category": payload.category,
            "seats_booked": payload.seats,
            "status": "Confirmed",
        }
    ).execute()

    supabase_admin.table("ticket_categories").update(
        {"available_seats": ticket_row["available_seats"] - payload.seats}
    ).eq("event_id", payload.event_id).eq("category", payload.category).execute()

    payment_id = f"PAY{int(time.time() * 1000)}"
    supabase_admin.table("payments").insert(
        {
            "payment_id": payment_id,
            "booking_id": booking_id,
            "user_id": current_user["user_id"],
            "amount": amount,
            "method": payload.payment_method,
            "status": "Success",
        }
    ).execute()

    return {
        "message": "Booking confirmed",
        "booking_id": booking_id,
        "payment_id": payment_id,
        "amount": amount,
    }


@router.get("/me")
def my_bookings(current_user: dict = Depends(get_current_user)):
    """
    Returns the logged-in user's bookings. This is the same data the
    AI Agent's get_user_booking_history tool returns, but for direct
    frontend use (e.g. a 'My Bookings' page) rather than chat.
    """
    result = (
        supabase_admin.table("bookings")
        .select("*")
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
    (trg_restore_seats) - no extra logic needed here.
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
