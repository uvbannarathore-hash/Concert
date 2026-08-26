"""
voice_db.py — DB/business-logic layer for the phone voice agent.

Ported from Clinigo's appointments_db.py. Key difference: Clinigo talked to
Postgres directly via psycopg2; this talks to Supabase via the existing
supabase_admin client (service-role), reusing the SAME tables/RPCs the
website, Telegram bot, and n8n workflows already use — so a booking made
over the phone is indistinguishable from any other booking in the system.
"""

import logging
import time
import uuid
import razorpay
from app.supabase_client import supabase_admin
from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET

logger = logging.getLogger("voice_db")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))


# ---------------------------------------------------------------------------
# Caller identity — find-or-create a user row by phone number.
# Mirrors Clinigo's "identify by phone" pattern, adapted to concert's
# users table (which normally requires signup, but the voice agent bypasses
# that and creates a minimal phone-only row on first call).
# ---------------------------------------------------------------------------
def find_or_create_user_by_phone(phone: str, name: str | None = None) -> dict:
    """
    Looks up a user by phone. If none exists, creates a minimal user row
    (phone only, no email/password) so bookings have a valid user_id to
    attach to. Returns {"success": True, "user_id": ..., "is_new": bool}.
    """
    phone = (phone or "").strip()
    if not phone:
        return {"success": False, "message": "A phone number is required to identify the caller."}

    existing = (
        supabase_admin.table("users")
        .select("user_id, name, is_admin")
        .eq("phone", phone)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        if row.get("is_admin"):
            return {"success": False, "message": "This phone number belongs to an admin account and cannot book tickets."}
        return {"success": True, "user_id": row["user_id"], "name": row.get("name"), "is_new": False}

    # No account yet — create a minimal phone-only user so the booking has
    # somewhere to attach. users.user_id is `text NOT NULL` with no DB
    # default (unlike Supabase-Auth-issued IDs used for website signups),
    # so we generate one here. Prefixed so these are easy to spot/filter
    # later (e.g. in admin reports) as voice-originated accounts.
    insert_payload = {"user_id": f"VOICE-{uuid.uuid4().hex[:12]}", "phone": phone}
    if name:
        insert_payload["name"] = name

    created = supabase_admin.table("users").insert(insert_payload).execute()
    if not created.data:
        logger.error(f"Failed to create phone-only user for {phone}")
        return {"success": False, "message": "Could not create a caller record. Please try again."}

    row = created.data[0]
    return {"success": True, "user_id": row["user_id"], "name": row.get("name"), "is_new": True}


# ---------------------------------------------------------------------------
# Event/ticket lookup — caller won't know an event_id, so search is
# name/city driven, like the Admin Agent's list_events tool.
# ---------------------------------------------------------------------------
def search_events(query: str | None = None, city: str | None = None) -> dict:
    """Searches upcoming events by artist/event name (partial match) and/or city."""
    q = supabase_admin.table("events").select("event_id, artist_name, venue_name, city, event_date, event_type")
    if city:
        q = q.eq("city", city)
    result = q.execute()

    rows = result.data or []
    if query:
        needle = query.strip().lower()
        rows = [r for r in rows if needle in (r.get("artist_name") or "").lower()]

    if not rows:
        return {"success": False, "message": f"No upcoming events found matching '{query or city}'."}

    lines = [
        f"{r['artist_name']} at {r['venue_name']}, {r['city']} on {r['event_date']} (event_id: {r['event_id']})"
        for r in rows
    ]
    return {"success": True, "message": "Found these events:\n" + "\n".join(lines), "events": rows}


def get_ticket_categories(event_id: str) -> dict:
    """Returns ticket categories, prices, and seat availability for an event."""
    result = (
        supabase_admin.table("ticket_categories")
        .select("category, price_inr, available_seats")
        .eq("event_id", event_id)
        .execute()
    )
    if not result.data:
        return {"success": False, "message": "No ticket categories found for this event."}

    lines = [
        f"{r['category']}: ₹{r['price_inr']} ({r['available_seats']} seats left)"
        for r in result.data
    ]
    return {"success": True, "message": "Available categories:\n" + "\n".join(lines), "categories": result.data}


# ---------------------------------------------------------------------------
# Booking — reuses the SAME book_ticket_transaction RPC + Razorpay
# payment-link pattern as the n8n "Create Booking With Payment Link"
# workflow, so seat-locking and payment confirmation logic isn't duplicated.
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Booking — reuses the SAME book_ticket_transaction RPC + Razorpay
# payment-link pattern as the n8n "Create Booking With Payment Link"
# workflow, so seat-locking and payment confirmation logic isn't duplicated.
# ---------------------------------------------------------------------------
def _create_booking_and_payment_link(user_id: str, event_id: str, category: str, seats: int,
                                      contact_phone: str | None, contact_name: str | None) -> dict:
    """Shared core: creates the pending booking (RPC) + Razorpay payment link. Used by
    both the phone-call flow (book_ticket) and the website flow (book_ticket_for_user)."""
    rpc_result = supabase_admin.rpc(
        "book_ticket_transaction",
        {
            "p_user_id": user_id,
            "p_event_id": event_id,
            "p_category": category,
            "p_seats_booked": seats,
        },
    ).execute()

    if not rpc_result.data or not rpc_result.data.get("booking_id"):
        return {"success": False, "message": "Booking could not be created — seats may no longer be available."}

    booking = rpc_result.data
    booking_id = booking["booking_id"]

    link_payload = {
        "amount": int(round(float(booking["total_price"]) * 100)),
        "currency": "INR",
        "description": f"{booking.get('artist_name', 'Event')} - {category} x{seats}",
        "customer": {"name": contact_name or "Guest"},
        "notify": {"sms": False, "email": False},
        "reminder_enable": True,
        "notes": {"booking_id": booking_id},
    }
    if contact_phone:
        link_payload["customer"]["contact"] = contact_phone
        link_payload["notify"]["sms"] = True

    payment_link = razorpay_client.payment_link.create(link_payload)

    supabase_admin.table("bookings").update(
        {"razorpay_payment_link_id": payment_link["id"], "booking_source": "voice_call" if contact_phone else "voice_website"}
    ).eq("booking_id", booking_id).execute()

    return {
        "success": True,
        "booking_id": booking_id,
        "payment_link": payment_link.get("short_url"),
        "message": (
            f"Booking created for {seats} {category} seat(s). Status is Pending Payment — "
            + (f"a payment link has been sent to {contact_phone} via SMS. " if contact_phone else "here is the payment link: " + (payment_link.get("short_url") or "") + ". ")
            + "Tell the caller their seats are held but the booking is confirmed only after payment."
        ),
    }


def book_ticket(caller_phone: str, event_id: str, category: str, seats: int, caller_name: str | None = None) -> dict:
    """Phone-call flow: caller isn't logged in, so identify/create the user by phone first."""
    identity = find_or_create_user_by_phone(caller_phone, caller_name)
    if not identity["success"]:
        return identity

    return _create_booking_and_payment_link(identity["user_id"], event_id, category, seats, caller_phone, caller_name)


def book_ticket_for_user(user_id: str, event_id: str, category: str, seats: int) -> dict:
    """Website STS flow: caller is already an authenticated user (LiveKit participant
    identity = user_id from the /voice/token JWT), so no phone lookup/guest creation needed."""
    profile = supabase_admin.table("users").select("phone, name, is_admin").eq("user_id", user_id).execute()
    if not profile.data:
        return {"success": False, "message": "Could not find your account."}
    if profile.data[0].get("is_admin"):
        return {"success": False, "message": "Admin accounts cannot book tickets."}

    contact_phone = profile.data[0].get("phone")
    contact_name = profile.data[0].get("name")
    return _create_booking_and_payment_link(user_id, event_id, category, seats, contact_phone, contact_name)


def get_booking_status(caller_phone: str) -> dict:
    """Looks up recent bookings for a phone-call caller by phone number."""
    user = (
        supabase_admin.table("users")
        .select("user_id")
        .eq("phone", caller_phone)
        .execute()
    )
    if not user.data:
        return {"success": False, "message": "No account found for this phone number."}

    return get_booking_status_for_user(user.data[0]["user_id"])


def get_booking_status_for_user(user_id: str) -> dict:
    """Website STS flow: looks up recent bookings directly by the authenticated user_id."""
    bookings = (
        supabase_admin.table("bookings")
        .select("booking_id, event_id, category, seats_booked, status, payment_status, events(artist_name, event_date)")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .limit(5)
        .execute()
    )
    if not bookings.data:
        return {"success": False, "message": "No bookings found for this account."}

    lines = [
        f"{b['booking_id']}: {b.get('events', {}).get('artist_name', 'Event')} — "
        f"{b['category']} x{b['seats_booked']}, status: {b['status']} ({b['payment_status']})"
        for b in bookings.data
    ]
    return {"success": True, "message": "Recent bookings:\n" + "\n".join(lines)}


def cancel_booking(caller_phone: str, booking_id: str) -> dict:
    """Cancels a booking for a phone-call caller. Identifies the caller by phone first."""
    user = supabase_admin.table("users").select("user_id").eq("phone", caller_phone).execute()
    if not user.data:
        return {"success": False, "message": "No account found for this phone number."}

    return cancel_booking_for_user(user.data[0]["user_id"], booking_id)


def cancel_booking_for_user(user_id: str, booking_id: str) -> dict:
    """Website STS flow: cancels a booking, filtered by booking_id AND the authenticated
    user_id, same rule enforced in booking_routes.cancel_booking."""
    result = (
        supabase_admin.table("bookings")
        .update({"status": "Cancelled"})
        .eq("booking_id", booking_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not result.data:
        return {"success": False, "message": "Booking not found, or it doesn't belong to this account."}

    return {"success": True, "message": f"Booking {booking_id} has been cancelled."}


# ---------------------------------------------------------------------------
# Call session logging — same shape as Clinigo's call_sessions table.
# Run this once (e.g. in a migration) before first use:
#
# CREATE TABLE IF NOT EXISTS call_sessions (
#     id SERIAL PRIMARY KEY,
#     session_id VARCHAR(100) UNIQUE NOT NULL,
#     caller_phone VARCHAR(20),
#     started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
#     ended_at TIMESTAMPTZ,
#     duration_seconds INTEGER,
#     transcript TEXT,
#     summary TEXT,
#     outcome VARCHAR(50)
# );
# ---------------------------------------------------------------------------
def log_call_session(session_id: str, caller_phone: str | None, started_at, ended_at,
                      transcript: str, summary: str = "", outcome: str = "") -> None:
    """Persists a call transcript/summary to call_sessions. Raises on failure —
    intentionally NOT swallowed here, so the caller (agent.py's
    _save_session_on_shutdown) can tell a real failure apart from success and
    log accordingly (e.g. its specific "table doesn't exist yet" warning).
    Swallowing the exception here previously caused agent.py to always log
    "Session saved" even when the insert failed."""
    duration = int((ended_at - started_at).total_seconds()) if ended_at and started_at else None
    supabase_admin.table("call_sessions").upsert(
        {
            "session_id": session_id,
            "caller_phone": caller_phone,
            "started_at": started_at.isoformat() if started_at else None,
            "ended_at": ended_at.isoformat() if ended_at else None,
            "duration_seconds": duration,
            "transcript": transcript,
            "summary": summary,
            "outcome": outcome,
        },
        on_conflict="session_id",
    ).execute()
    logger.info(f"Call session saved: {session_id} | Duration: {duration}s | Outcome: {outcome}")