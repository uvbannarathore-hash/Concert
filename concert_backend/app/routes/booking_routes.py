import time
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.auth import get_current_user
from app.supabase_client import supabase_admin

router = APIRouter(prefix="/bookings", tags=["bookings"])


class CreateBookingRequest(BaseModel):
    event_id: str
    category: str
    seats: int
    payment_method: str = "Card"


@router.post("")
def create_booking(payload: CreateBookingRequest, current_user: dict = Depends(get_current_user)):
    # ---------------- ADMIN BLOCK CHECK ----------------
    if current_user.get("is_admin") is True:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin accounts are not permitted to book tickets. Please use a regular customer account."
        )
    # ----------------------------------------------------

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
    result = (
        supabase_admin.table("bookings")
        .select("*, events(*)")
        .eq("user_id", current_user["user_id"])
        .execute()
    )
    return {"bookings": result.data}


@router.post("/{booking_id}/cancel")
def cancel_booking(booking_id: str, current_user: dict = Depends(get_current_user)):
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