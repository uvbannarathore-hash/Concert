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
from datetime import date, datetime, timedelta
from calendar import monthrange
from zoneinfo import ZoneInfo
from app.supabase_client import supabase_admin
from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
from app.services.cancellation_service import get_cancellation_eligibility, initiate_cancellation

logger = logging.getLogger("voice_db")

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

def resolve_temporal_intent(intent: str | None, specific_month: int | None = None) -> tuple[str | None, str | None]:
    """
    Resolves temporal intents into deterministic ISO string bounds [start, end)
    using the Asia/Kolkata timezone.
    """
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    start_date = None
    end_date = None
    
    if specific_month:
        y = now.year
        if specific_month < now.month:
            y += 1
        start_date = datetime(y, specific_month, 1).date()
        _, last_day = monthrange(y, specific_month)
        end_date = start_date + timedelta(days=last_day)
        return start_date.isoformat(), end_date.isoformat()

    if not intent or intent == "ALL":
        return None, None
        
    today = now.date()
    
    if intent == "TODAY":
        start_date = today
        end_date = today + timedelta(days=1)
    elif intent == "TOMORROW":
        start_date = today + timedelta(days=1)
        end_date = start_date + timedelta(days=1)
    elif intent == "THIS_WEEK":
        # Monday to Sunday
        start_date = today - timedelta(days=today.weekday())
        end_date = start_date + timedelta(days=7)
    elif intent == "THIS_WEEKEND":
        # Saturday to Sunday
        saturday = today + timedelta(days=(5 - today.weekday()))
        if today.weekday() >= 5: # If it's already weekend, weekend is this Saturday
            saturday = today - timedelta(days=(today.weekday() - 5))
        start_date = saturday
        end_date = saturday + timedelta(days=2)
    elif intent == "NEXT_WEEKEND":
        saturday = today + timedelta(days=(5 - today.weekday()))
        if today.weekday() >= 5:
            saturday = today - timedelta(days=(today.weekday() - 5))
        saturday = saturday + timedelta(days=7)
        start_date = saturday
        end_date = saturday + timedelta(days=2)
    elif intent == "NEXT_WEEK":
        start_date = today + timedelta(days=(7 - today.weekday()))
        end_date = start_date + timedelta(days=7)
    elif intent == "THIS_MONTH":
        start_date = today.replace(day=1)
        _, last_day = monthrange(today.year, today.month)
        end_date = start_date + timedelta(days=last_day)
    elif intent == "NEXT_MONTH":
        y, m = today.year, today.month
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
        start_date = today.replace(year=y, month=m, day=1)
        _, last_day = monthrange(y, m)
        end_date = start_date + timedelta(days=last_day)
    elif intent.startswith("THIS_") or intent.startswith("NEXT_"):
        # Handle specific days like THIS_SATURDAY, NEXT_TUESDAY
        days_of_week = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
        parts = intent.split("_")
        if len(parts) == 2 and parts[1] in days_of_week:
            target_weekday = days_of_week.index(parts[1])
            current_weekday = today.weekday()
            
            # Days ahead to the next occurrence of that weekday
            days_ahead = target_weekday - current_weekday
            if days_ahead <= 0:
                days_ahead += 7
                
            if parts[0] == "NEXT":
                days_ahead += 7
                
            start_date = today + timedelta(days=days_ahead)
            # If it's today and they said "THIS_TUESDAY" and today is Tuesday, days_ahead is 7.
            # But normally "this Tuesday" when today is Tuesday means today. Let's adjust:
            if parts[0] == "THIS" and days_ahead == 7:
                days_ahead = 0
                start_date = today
                
            end_date = start_date + timedelta(days=1)
        
    if start_date and end_date:
        return start_date.isoformat(), end_date.isoformat()
    return None, None


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
def search_events(query: str | None = None, city: str | None = None, temporal_intent: str | None = None, specific_month: int | None = None, status_filter: str | None = None) -> dict:
    """Searches upcoming events by artist/event name, city, and temporal constraint."""
    from app.services.embedding_service import generate_query_embedding
    today = datetime.now(ZoneInfo("Asia/Kolkata")).date().isoformat()
    
    start_date, end_date = resolve_temporal_intent(temporal_intent, specific_month)
    
    candidate_ids: list[str] | None = None
    similarity_rank: dict[str, float] = {}
    
    if query:
        # If the query is literally "sold out" or similar, the AI might pass it. 
        # But we still run it through pgvector just in case there's semantic meaning.
        embedding = generate_query_embedding(query)
        if embedding:
            rpc = supabase_admin.rpc(
                "match_events",
                {"query_embedding": embedding, "match_threshold": 0.6, "match_count": 20},
            ).execute()
            if rpc.data:
                candidate_ids = [m["event_id"] for m in rpc.data]
                similarity_rank = {m["event_id"]: m["similarity"] for m in rpc.data}
            else:
                candidate_ids = []

    if candidate_ids is not None and len(candidate_ids) == 0:
        return {
            "success": False,
            "message": f"No upcoming events found matching '{query}'.",
        }

    q = (
        supabase_admin
        .table("events")
        .select(
            "event_id, artist_name, venue_name, city, event_date, event_time, "
            "event_type, status, ticket_categories(category, price_inr)"
        )
    )

    if status_filter:
        q = q.eq("status", status_filter)
    else:
        q = q.in_("status", ["Upcoming", "Sold Out"])

    if candidate_ids is not None:
        q = q.in_("event_id", candidate_ids)

    if start_date and end_date:
        q = q.gte("event_date", start_date).lt("event_date", end_date)
    else:
        q = q.gte("event_date", today)

    if city:
        q = q.ilike("city", f"%{city}%")

    result = q.execute()

    rows = result.data or []

    if not rows:
        qualifier = " ".join(filter(None, [query, city]))
        return {
            "success": False,
            "message": f"No upcoming events found{f' matching {qualifier!r}' if qualifier else ''}."
        }

    # Re-apply similarity ranking so results stay most-relevant-first.
    if similarity_rank:
        rows.sort(key=lambda r: similarity_rank.get(r["event_id"], 0.0), reverse=True)
    else:
        rows.sort(key=lambda r: r["event_date"])

    lines = []
    for r in rows:
        cats = r.get("ticket_categories") or []
        cat_details = ", ".join(f"{c['category']}: INR {c['price_inr']:,.0f}" for c in cats if c.get("price_inr") is not None)
        price_str = f"[{cat_details}]" if cat_details else "price TBA"
        status_tag = " [SOLD OUT]" if r.get("status") == "Sold Out" else ""
        lines.append(
            f"{r['artist_name']} at {r['venue_name']}, {r['city']} "
            f"on {r['event_date']} at {r.get('event_time', 'time TBA')}{status_tag} "
            f"| Tickets: {price_str} (event_id: {r['event_id']})"
        )

    return {
        "success": True,
        "message": "Found these events:\n" + "\n".join(lines),
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


def get_booking_status(caller_phone: str, temporal_intent: str | None = None, specific_month: int | None = None) -> dict:
    """Looks up recent bookings for a phone-call caller by phone number."""
    user = (
        supabase_admin.table("users")
        .select("user_id")
        .eq("phone", caller_phone)
        .execute()
    )
    if not user.data:
        return {"success": False, "message": "No account found for this phone number."}

    return get_booking_status_for_user(user.data[0]["user_id"], temporal_intent, specific_month)


def get_booking_status_for_user(user_id: str, temporal_intent: str | None = None, specific_month: int | None = None) -> dict:
    """Website STS flow: looks up recent bookings directly by the authenticated user_id."""
    start_date, end_date = resolve_temporal_intent(temporal_intent, specific_month)
    
    q = (
        supabase_admin.table("bookings")
        .select("booking_id, event_id, category, seats_booked, status, payment_status, events!inner(artist_name, event_date)", count="exact")
        .eq("user_id", user_id)
    )
    
    if start_date and end_date:
        q = q.gte("events.event_date", start_date).lt("events.event_date", end_date)
        
    bookings = q.order("created_at", desc=True).limit(10).execute()
    
    if not bookings.data:
        return {"success": False, "message": "No bookings found for this account matching the criteria.", "total_count": 0, "returned_count": 0, "has_more": False}

    lines = [
        f"{b['booking_id']}: {b.get('events', {}).get('artist_name', 'Event')} (Event Date: {b.get('events', {}).get('event_date')}) — "
        f"{b['category']} x{b['seats_booked']}, status: {b['status']} ({b['payment_status']})"
        for b in bookings.data
    ]
    
    total_count = bookings.count if bookings.count is not None else len(bookings.data)
    returned_count = len(bookings.data)
    has_more = total_count > returned_count
    
    msg = f"Found {total_count} matching booking(s)."
    if has_more:
        msg += f" Showing the {returned_count} most recent ones:"
    else:
        msg += ":"
    msg += "\n" + "\n".join(lines)
        
    return {
        "success": True, 
        "message": msg,
        "total_count": total_count,
        "returned_count": returned_count,
        "has_more": has_more,
        "bookings": bookings.data
    }


def cancel_booking(caller_phone: str, booking_id: str) -> dict:
    """Cancels a booking for a phone-call caller. Identifies the caller by phone first."""
    user = supabase_admin.table("users").select("user_id").eq("phone", caller_phone).execute()
    if not user.data:
        return {"success": False, "message": "No account found for this phone number."}

    return cancel_booking_for_user(user.data[0]["user_id"], booking_id)


def check_cancellation_eligibility_for_phone(caller_phone: str, booking_id: str) -> dict:
    """Phone-call flow: resolves the caller by phone, then checks cancellation
    eligibility/refund breakdown for one of their bookings, reusing the same
    cancellation_service.get_cancellation_eligibility used by the website and
    chat agent - never a second policy implementation."""
    user = supabase_admin.table("users").select("user_id").eq("phone", caller_phone).execute()
    if not user.data:
        return {"eligible": False, "reason": "No account found for this phone number.", "refund_amount": 0}

    return get_cancellation_eligibility(booking_id, user.data[0]["user_id"])


def get_user_hosted_shows_for_phone(caller_phone: str) -> dict:
    """Phone-call flow: resolves the caller by phone, then looks up their
    submitted/hosted shows via the same query get_user_hosted_shows() uses
    for the website/Telegram flow."""
    user = supabase_admin.table("users").select("user_id").eq("phone", caller_phone).execute()
    if not user.data:
        return {"success": False, "message": "No account found for this phone number."}

    return get_user_hosted_shows(user.data[0]["user_id"])


def cancel_booking_for_user(user_id: str, booking_id: str) -> dict:
    """Website/Telegram/Voice flow: cancels a booking, filtered by booking_id
    AND the authenticated user_id, same rule enforced in
    booking_routes.cancel_booking.

    Delegates to cancellation_service.initiate_cancellation(), the single
    shared implementation of the atomic claim / Razorpay refund-reconciliation
    / final-update flow (also used by the REST /cancel endpoint). This used
    to have its own separate, unguarded razorpay_client.payment.refund() call
    here - that duplicate implementation had no existing-refund check at all,
    so any retry (including a voice caller saying "cancel it" twice, or a
    chat/voice + website race) could attempt a second refund for an amount
    Razorpay had already refunded. Reusing initiate_cancellation() fixes that
    and keeps refund logic in exactly one place. It also already performs the
    same atomic "Cancellation Processing" claim + single final update that
    the Postgres trigger watches for seat restoration and the cancellation
    email - so the separate send-booking-notifications call that used to be
    here has been removed to avoid a duplicate email.
    """
    booking_check = (
        supabase_admin.table("bookings")
        .select("booking_id")
        .eq("booking_id", booking_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not booking_check.data:
        return {"success": False, "message": "Booking not found, or it doesn't belong to this account."}

    result = initiate_cancellation(booking_id, user_id)
    if not result.get("success"):
        return result

    refund_amount = result.get("refund_amount")
    if refund_amount:
        result["message"] = f"{result.get('message', 'Booking cancelled')}. Expected refund: INR {refund_amount}"
    return result

def get_user_hosted_shows(user_id: str) -> dict:
    """Website/Telegram STS flow: looks up the user's submitted/hosted shows from show_submissions."""
    result = (
        supabase_admin.table("show_submissions")
        .select("artist_name, venue_name, event_date, status")
        .eq("submitted_by_user_id", user_id)
        .order("created_at", desc=True)
        .limit(10)
        .execute()
    )
    
    if not result.data:
        return {"success": False, "message": "You haven't hosted or submitted any shows yet."}

    lines = [
        f"Show: {row.get('artist_name')} at {row.get('venue_name')} on {row.get('event_date')} (Status: {row.get('status')})"
        for row in result.data
    ]
    return {"success": True, "message": "Your hosted shows:\n" + "\n".join(lines)}


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