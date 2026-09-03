"""
dograh_routes.py — REST endpoints for the Dograh voice agent's HTTP API Tools.

Dograh (app.dograh.com / self-hosted) is a workflow-based voice AI platform.
It runs its own STT/LLM/TTS pipeline on its own infrastructure and, mid-call,
invokes plain REST endpoints ("HTTP API Tools") that you attach to Agent
nodes in its workflow builder. This is the equivalent of voice_agent/tools.py
(the old LiveKit @function_tool definitions) but reachable over HTTP instead
of being called in-process by a Python LLM SDK.

This replaces the entire voice_agent/ package as the live voice-booking
path: no LiveKit worker, no Cartesia/Groq/Gemini clients, no VAD — just
thin wrappers around the SAME voice_db.py business logic already used by
the phone (Tata) and website (LiveKit) voice agents, so a booking made via
Dograh is indistinguishable in the database from any other booking.

AUTH: Dograh cannot perform your Supabase JWT login flow, so these
endpoints are protected by a single shared secret instead — sent by Dograh
on every tool call as the `X-Dograh-Tool-Key` header. Configure the same
value in:
  1. This backend's .env as DOGRAH_TOOL_API_KEY
  2. Each HTTP API Tool in Dograh, as a custom header:
       X-Dograh-Tool-Key: <same value>

Do NOT expose these endpoints without this header check — book_ticket and
cancel_booking are mutating and unauthenticated beyond the shared secret.
"""

import logging

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.config import DOGRAH_TOOL_API_KEY
from app.voice_agent import voice_db

logger = logging.getLogger("dograh_routes")

router = APIRouter(prefix="/dograh", tags=["dograh-voice-tools"])


def _check_tool_key(x_dograh_tool_key: str | None) -> None:
    if not DOGRAH_TOOL_API_KEY:
        # Fail closed: if the secret isn't configured on the server, refuse
        # every call instead of silently running these endpoints open.
        raise HTTPException(
            status_code=500,
            detail="DOGRAH_TOOL_API_KEY is not configured on the server.",
        )
    if x_dograh_tool_key != DOGRAH_TOOL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing tool key.")


# ---------------------------------------------------------------------------
# 1. search_events
# ---------------------------------------------------------------------------
@router.get("/search-events")
def dograh_search_events(
    query: str = "",
    city: str = "",
    x_dograh_tool_key: str | None = Header(default=None),
):
    """Search upcoming events by artist/event name and/or city."""
    _check_tool_key(x_dograh_tool_key)
    logger.info(f"[dograh] search_events query={query!r} city={city!r}")
    result = voice_db.search_events(query or None, city or None)
    return result


# ---------------------------------------------------------------------------
# 2. get_ticket_categories
# ---------------------------------------------------------------------------
@router.get("/ticket-categories")
def dograh_ticket_categories(
    event_id: str,
    x_dograh_tool_key: str | None = Header(default=None),
):
    """Get ticket categories, prices, and seat availability for an event."""
    _check_tool_key(x_dograh_tool_key)
    logger.info(f"[dograh] get_ticket_categories event_id={event_id!r}")
    result = voice_db.get_ticket_categories(event_id)
    return result


# ---------------------------------------------------------------------------
# 3. book_ticket
# ---------------------------------------------------------------------------
class BookTicketBody(BaseModel):
    event_id: str
    category: str
    seats: int
    caller_phone: str
    caller_name: str = ""


@router.post("/book-ticket")
def dograh_book_ticket(
    body: BookTicketBody,
    x_dograh_tool_key: str | None = Header(default=None),
):
    """Book concert tickets. Requires event_id, category, seats, and the
    caller's phone number (used to identify/create the caller's account)."""
    _check_tool_key(x_dograh_tool_key)
    logger.info(
        f"[dograh] book_ticket event_id={body.event_id!r} category={body.category!r} "
        f"seats={body.seats} phone={body.caller_phone!r}"
    )
    result = voice_db.book_ticket(
        body.caller_phone, body.event_id, body.category, body.seats, body.caller_name or None
    )
    return result


# ---------------------------------------------------------------------------
# 4. get_booking_status
# ---------------------------------------------------------------------------
@router.get("/booking-status")
def dograh_booking_status(
    caller_phone: str,
    x_dograh_tool_key: str | None = Header(default=None),
):
    """Check a caller's existing bookings by phone number."""
    _check_tool_key(x_dograh_tool_key)
    logger.info(f"[dograh] get_booking_status phone={caller_phone!r}")
    result = voice_db.get_booking_status(caller_phone)
    return result


# ---------------------------------------------------------------------------
# 5. cancel_booking
# ---------------------------------------------------------------------------
class CancelBookingBody(BaseModel):
    caller_phone: str
    booking_id: str


@router.post("/cancel-booking")
def dograh_cancel_booking(
    body: CancelBookingBody,
    x_dograh_tool_key: str | None = Header(default=None),
):
    """Cancel one of the caller's bookings. booking_id must come from
    get_booking_status — never invent one."""
    _check_tool_key(x_dograh_tool_key)
    logger.info(
        f"[dograh] cancel_booking phone={body.caller_phone!r} booking_id={body.booking_id!r}"
    )
    result = voice_db.cancel_booking(body.caller_phone, body.booking_id)
    return result