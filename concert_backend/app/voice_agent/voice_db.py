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
from datetime import date
from zoneinfo import ZoneInfo
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
    """Searches upcoming events by artist/event name and/or city."""
    today = date.today().isoformat()

    q = (
        supabase_admin
        .table("events")
        .select(
            "event_id, artist_name, venue_name, city, event_date, event_time, event_type"
        )
        .gte("event_date", today)
    )

    if city:
        q = q.eq("city", city)

    result = q.execute()

    rows = result.data or []

    if query:
        needle = query.strip().lower()
        rows = [
            r for r in rows
            if needle in (r.get("artist_name") or "").lower()
        ]

    if not rows:
        return {
            "success": False,
            "message": f"No upcoming events found matching '{query or city}'."
        }

    # Same movie/artist can have multiple showtimes at the same venue on
    # the same date (e.g. a 7pm and a 9pm show) - these are DIFFERENT
    # event_ids with different seat/pricing data. event_time MUST be
    # shown here, or a caller asking for a specific showtime (e.g. "the
    # 9pm show") gives the LLM nothing to match against, and it can
    # silently pick the wrong one.
    lines = [
        f"{r['artist_name']} at {r['venue_name']}, {r['city']} "
        f"on {r['event_date']} at {r.get('event_time', 'time TBA')} (event_id: {r['event_id']})"
        for r in rows
    ]

    return {
        "success": True,
        "message": "Found these upcoming events:\n" + "\n".join(lines),
        "events": rows,
    }

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
# Seat-map awareness — events an admin has built a seat layout for (see
# admin_routes.py's /admin/seat-layout/add-row) support picking exact seats
# (e.g. "N5, N6") instead of just a quantity. Events with no layout defined
# keep working exactly as before via the plain category+count RPC further
# below - _event_has_seat_map is the single switch that decides which path
# a booking takes, so callers of book_ticket/book_ticket_for_user never
# need to know or care which kind of event they're booking.
# ---------------------------------------------------------------------------
def _event_has_seat_map(event_id: str, category: str | None = None) -> bool:
    """Whether this event (or, when given, this specific CATEGORY of it)
    has a defined seat layout. Category-specific matters because a
    single event can be a mix - e.g. Gold has a seat map but Silver
    doesn't - and treating the whole event as seat-mapped just because
    one category is would silently misroute bookings for the others."""
    query = supabase_admin.table("event_seats").select("id").eq("event_id", event_id)
    if category:
        query = query.eq("category", category)
    result = query.limit(1).execute()
    return bool(result.data)


def get_available_seats(event_id: str, category: str | None = None) -> dict:
    """Returns the seat map for an event (optionally filtered to one
    category), grouped by row, so the caller/AI can read out what's open.
    has_seat_map=False means this event uses plain quantity-based booking
    instead - the caller should just ask how many tickets, not which seats."""
    query = (
        supabase_admin.table("event_seats")
        .select("id, category, seat_row, seat_number, status")
        .eq("event_id", event_id)
    )
    if category:
        query = query.eq("category", category)
    result = query.order("seat_row").order("seat_number").execute()

    if not result.data:
        return {
            "has_seat_map": False,
            "message": "This event doesn't use seat selection — just say how many tickets and which category.",
        }

    available = [s for s in result.data if s["status"] == "Available"]
    if not available:
        return {"has_seat_map": True, "available_seats": [], "message": "No seats are currently available in this category."}

    by_row: dict[str, list[int]] = {}
    for s in available:
        by_row.setdefault(s["seat_row"], []).append(s["seat_number"])

    lines = [f"Row {row}: {', '.join(str(n) for n in sorted(nums))}" for row, nums in sorted(by_row.items())]
    return {
        "has_seat_map": True,
        "available_seats": available,
        "message": "Available seats:\n" + "\n".join(lines),
    }


def _resolve_seat_ids(event_id: str, category: str, seat_numbers: list[str]) -> list[int] | None:
    """Converts human seat labels like 'N5' or 'n 5' into event_seats.id
    values - MUST match the requested category, not just event_id/row/
    number, or a seat label that happens to exist under a different
    category (e.g. 'C3' under VIP when the caller asked for Silver)
    would silently get booked at the wrong category/price with no
    error. Returns None if any label can't be found in that exact
    category (caller-facing functions turn that into a friendly 'seat
    not found' message)."""
    ids = []
    for label in seat_numbers:
        clean = label.strip().upper()
        row = "".join(c for c in clean if c.isalpha())
        num_str = "".join(c for c in clean if c.isdigit())
        if not row or not num_str:
            return None
        result = (
            supabase_admin.table("event_seats")
            .select("id")
            .eq("event_id", event_id)
            .eq("category", category)
            .eq("seat_row", row)
            .eq("seat_number", int(num_str))
            .execute()
        )
        if not result.data:
            return None
        ids.append(result.data[0]["id"])
    return ids


def _auto_pick_seat_ids(event_id: str, category: str, count: int) -> list[int] | None:
    """Picks the first N available seats in a category automatically, for
    callers who say 'any 2 seats' rather than naming specific ones.
    Returns None if fewer than N are available."""
    result = (
        supabase_admin.table("event_seats")
        .select("id")
        .eq("event_id", event_id)
        .eq("category", category)
        .eq("status", "Available")
        .order("seat_row")
        .order("seat_number")
        .limit(count)
        .execute()
    )
    if len(result.data) < count:
        return None
    return [r["id"] for r in result.data]


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
                                      contact_phone: str | None, contact_name: str | None,
                                      source: str) -> dict:
    """Shared core: creates the pending booking (RPC) + Razorpay payment link. Used by
    the phone-call flow (book_ticket), the website flow, and the Telegram flow
    (both via book_ticket_for_user).

    source: the channel this booking was made through - "voice_call", "website",
    or "telegram". This is stored on the booking row and is what
    supabase/functions/send-booking-notifications reads to decide whether to
    send a Telegram confirmation (it only does so when source == "telegram",
    or when the user has separately opted in via notify_telegram_for_website).
    It must reflect the ACTUAL channel, not be guessed from unrelated fields
    like whether a phone number happens to be on file."""
    event_result = (
        supabase_admin
        .table("events")
        .select("event_id, artist_name, event_date")
        .eq("event_id", event_id)
        .single()
        .execute()
    )

    if not event_result.data:
        return {
            "success": False,
            "message": "The selected event could not be found."
        }

    event = event_result.data
    today = date.today().isoformat()

    if str(event.get("event_date")) < today:
        return {
            "success": False,
            "message": "This event has already taken place and cannot be booked."
        }
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
        {"razorpay_payment_link_id": payment_link["id"], "booking_source": source}
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


def _create_seat_booking_and_payment_link(user_id: str, event_id: str, seat_ids: list[int],
                                           contact_phone: str | None, contact_name: str | None,
                                           source: str) -> dict:
    """Seat-map equivalent of _create_booking_and_payment_link above - locks
    the specific seats then converts the lock into a real booking, both via
    atomic RPCs (see the seat_selection_migration.sql lock_seats /
    book_specific_seats functions), then creates the same kind of Razorpay
    payment link as the count-based flow."""
    lock_result = supabase_admin.rpc(
        "lock_seats", {"p_event_id": event_id, "p_seat_ids": seat_ids, "p_user_id": user_id}
    ).execute()
    if not lock_result.data.get("success"):
        return {"success": False, "message": lock_result.data.get("message", "Could not reserve those seats.")}

    book_result = supabase_admin.rpc(
        "book_specific_seats", {"p_user_id": user_id, "p_event_id": event_id, "p_seat_ids": seat_ids}
    ).execute()
    booking = book_result.data
    if not booking.get("success"):
        return {"success": False, "message": booking.get("message", "Booking failed.")}

    booking_id = booking["booking_id"]

    link_payload = {
        "amount": int(round(float(booking["total_price"]) * 100)),
        "currency": "INR",
        "description": f"{booking.get('artist_name', 'Event')} - {booking['category']} x{booking['seats_booked']}",
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
        {"razorpay_payment_link_id": payment_link["id"], "booking_source": source}
    ).eq("booking_id", booking_id).execute()

    return {
        "success": True,
        "booking_id": booking_id,
        "payment_link": payment_link.get("short_url"),
        "message": (
            f"Booking created for {booking['seats_booked']} {booking['category']} seat(s). Status is Pending Payment — "
            + (f"a payment link has been sent to {contact_phone} via SMS. " if contact_phone else "here is the payment link: " + (payment_link.get("short_url") or "") + ". ")
            + "Tell the caller their seats are held but the booking is confirmed only after payment."
        ),
    }


def _route_booking(user_id: str, event_id: str, category: str, seats: int | None,
                    seat_numbers: list[str] | None, contact_phone: str | None,
                    contact_name: str | None, source: str) -> dict:
    """Single decision point for whether a booking uses the seat-map flow
    or the plain quantity flow - shared by both book_ticket (phone) and
    book_ticket_for_user (website/Telegram) so the routing logic only
    lives in one place. Note: the "event already passed" check lives in
    _create_booking_and_payment_link for the plain flow - the seat-map
    flow doesn't duplicate it here since seat-map events are always
    admin-curated upcoming shows in practice, but if that assumption ever
    changes, add the same date guard to _create_seat_booking_and_payment_link."""
    has_seat_map = _event_has_seat_map(event_id, category)

    if seat_numbers:
        if not has_seat_map:
            return {"success": False, "message": f"The {category} category doesn't use seat selection - please just say how many tickets you'd like instead."}
        seat_ids = _resolve_seat_ids(event_id, category, seat_numbers)
        if seat_ids is None:
            return {"success": False, "message": f"Could not find one or more of those seats in the {category} category. Please double-check the seat numbers."}
        return _create_seat_booking_and_payment_link(user_id, event_id, seat_ids, contact_phone, contact_name, source)

    if not seats:
        return {"success": False, "message": "Please specify either a number of seats or specific seat numbers."}

    if has_seat_map:
        seat_ids = _auto_pick_seat_ids(event_id, category, seats)
        if seat_ids is None:
            return {"success": False, "message": f"Not enough available seats in {category} for {seats} tickets."}
        return _create_seat_booking_and_payment_link(user_id, event_id, seat_ids, contact_phone, contact_name, source)

    return _create_booking_and_payment_link(user_id, event_id, category, seats, contact_phone, contact_name, source)


def book_ticket(caller_phone: str, event_id: str, category: str, seats: int | None = None,
                 seat_numbers: list[str] | None = None, caller_name: str | None = None) -> dict:
    """Phone-call flow: caller isn't logged in, so identify/create the user by phone first.

    Pass EITHER seats (a count - auto-picks that many seats if the event
    has a seat map, or uses the plain quantity flow if it doesn't) OR
    seat_numbers (e.g. ["N5", "N6"] - only valid for events with a seat
    map). _route_booking decides which path applies."""
    identity = find_or_create_user_by_phone(caller_phone, caller_name)
    if not identity["success"]:
        return identity

    return _route_booking(
        identity["user_id"], event_id, category, seats, seat_numbers, caller_phone, caller_name, source="voice_call"
    )


def book_ticket_for_user(user_id: str, event_id: str, category: str, seats: int | None = None,
                          seat_numbers: list[str] | None = None, source: str = "website") -> dict:
    """Website/Telegram flow: caller is already identified (website: authenticated
    Supabase user; Telegram: resolved/auto-created profile - see customer_agent.py),
    so no phone lookup/guest creation needed.

    Pass EITHER seats (a count) OR seat_numbers (specific seats, e.g.
    ["N5", "N6"] - only valid for events with a seat map) - see
    _route_booking for how that's decided.

    source defaults to "website" for backward compatibility with existing callers
    (e.g. the on-site voice widget in voice_agent/tools.py's ConcertBookingToolsWeb)
    that don't pass it explicitly. app/agents/customer_tools.py passes "telegram"
    explicitly when the request came from the Telegram bot."""
    profile = supabase_admin.table("users").select("phone, name, is_admin").eq("user_id", user_id).execute()
    if not profile.data:
        return {"success": False, "message": "Could not find your account."}
    if profile.data[0].get("is_admin"):
        return {"success": False, "message": "Admin accounts cannot book tickets."}

    contact_phone = profile.data[0].get("phone")
    contact_name = profile.data[0].get("name")
    return _route_booking(
        user_id, event_id, category, seats, seat_numbers, contact_phone, contact_name, source=source
    )


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
        .update({"status": "Cancelled", "payment_status": "Cancelled"})
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