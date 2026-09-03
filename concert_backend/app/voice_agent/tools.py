"""
tools.py — LLM function-calling tools for the concert voice agent.
Written for LiveKit Agents 1.7's native @function_tool decorator.

IMPORTANT: as of livekit-agents 1.7, @function_tool reads the tool
description AND each parameter's description from a Google-style
docstring (via docstring_parser) — NOT from Annotated[..., TypeInfo(...)]
metadata (that was the pre-1.x pattern this file used to use, ported
from Clinigo). Every tool below must keep its "Args:" docstring block
in sync with its actual parameters, or the LLM silently loses
per-parameter guidance (no crash — schema generation just omits the
description).

@function_tool works fine as a plain-class method decorator (it
implements the descriptor protocol), so ConcertBookingTools and
ConcertBookingToolsWeb below don't need to subclass anything special —
agent.py just does getattr(toolset_instance, tool_name) to collect the
bound FunctionTool objects.

NOTE: every tool method here MUST be declared `async def`. LiveKit's
tool_executor.py always does `output = await tool(*fnc_args, **fnc_kwargs)`
regardless of whether the tool itself needs to await anything.

LATENCY FIX: the voice_db.* calls are synchronous (supabase-py sync
client) blocking HTTP round-trips. Calling them directly inside an
`async def` does NOT make them non-blocking - they still run on and
block the single asyncio event loop that LiveKit's whole audio/VAD/turn
pipeline shares, for the entire duration of the HTTP request (commonly
100ms-1s+). Every tool call below now wraps its voice_db call in
asyncio.to_thread(...), which runs it in a worker thread instead,
keeping the event loop free to keep processing audio while the DB/HTTP
call is in flight - this was contributing to the "every response feels
a bit slow" latency, especially on any turn that invokes a tool.
"""

import asyncio
import logging
from livekit.agents import function_tool
from app.voice_agent import voice_db

logger = logging.getLogger("voice_tools")


class ConcertBookingTools:
    """Tools exposed to the LLM agent for booking tickets for all supported event types over a phone call."""

    @function_tool
    async def search_events(self, query: str = "", city: str = "") -> str:
        """Search for upcoming events by artist name and/or city. Use this first to find
        the event_id before checking tickets or booking.

        Args:
            query: Artist or event name to search for, e.g. 'Arijit Singh'. Leave empty to just filter by city.
            city: City to filter by, e.g. 'Indore'. Optional.
        """
        logger.info(f"Executing Tool search_events query={query}, city={city}")
        res = await asyncio.to_thread(voice_db.search_events, query or None, city or None)
        return res["message"]

    @function_tool
    async def get_ticket_categories(self, event_id: str) -> str:
        """Get ticket categories, prices, and seat availability for a specific event.
        Requires the event_id from search_events.

        Args:
            event_id: The event_id returned by search_events.
        """
        logger.info(f"Executing Tool get_ticket_categories event_id={event_id}")
        res = await asyncio.to_thread(voice_db.get_ticket_categories, event_id)
        return res["message"]

    @function_tool
    async def book_ticket(
        self,
        event_id: str,
        category: str,
        seats: int,
        caller_phone: str,
        caller_name: str = "",
    ) -> str:
        """Book tickets for the caller for any supported event type.
Must collect event_id, category, number of seats, and confirm the
caller before calling this.

Args:
    event_id: The event_id to book.
    category: Ticket category, e.g. 'VIP', 'Gold', 'Silver' — must match get_ticket_categories exactly.
    seats: Number of seats to book.
    caller_phone: The caller's phone number (from caller ID or confirmed verbally).
    caller_name: The caller's name.
"""
        logger.info(f"Executing Tool book_ticket event_id={event_id}, category={category}, seats={seats}, phone={caller_phone}")
        res = await asyncio.to_thread(
            voice_db.book_ticket, caller_phone, event_id, category, seats, caller_name or None
        )
        return res["message"]

    @function_tool
    async def get_booking_status(self, caller_phone: str) -> str:
        """Check the status of a caller's existing bookings using their phone number.

        Args:
            caller_phone: The caller's phone number.
        """
        logger.info(f"Executing Tool get_booking_status phone={caller_phone}")
        res = await asyncio.to_thread(voice_db.get_booking_status, caller_phone)
        return res["message"]

    @function_tool
    async def cancel_booking(self, caller_phone: str, booking_id: str) -> str:
        """Cancel one of the caller's existing bookings. Must confirm the booking_id with
        the caller (from get_booking_status) before calling this.

        Args:
            caller_phone: The caller's phone number.
            booking_id: The booking_id to cancel.
        """
        logger.info(f"Executing Tool cancel_booking phone={caller_phone}, booking_id={booking_id}")
        res = await asyncio.to_thread(voice_db.cancel_booking, caller_phone, booking_id)
        return res["message"]


class ConcertBookingToolsWeb:
    """
    Tools for the WEBSITE speech-to-speech assistant. The caller is an
    authenticated logged-in user (LiveKit participant identity = user_id,
    set at token issuance in voice_routes.py) — so unlike the phone-call
    tools above, these never ask for or take a phone number; identity is
    already known and bound in at construction time.
    """

    def __init__(self, user_id: str):
        self.user_id = user_id

    @function_tool
    async def search_events(self, query: str = "", city: str = "") -> str:
        """Search for upcoming events by artist name and/or city. Use this first to find
        the event_id before checking tickets or booking.

        Args:
            query: Artist or event name to search for, e.g. 'Arijit Singh'. Leave empty to just filter by city.
            city: City to filter by, e.g. 'Indore'. Optional.
        """
        logger.info(f"[web:{self.user_id}] Executing Tool search_events query={query}, city={city}")
        res = await asyncio.to_thread(voice_db.search_events, query or None, city or None)
        return res["message"]

    @function_tool
    async def get_ticket_categories(self, event_id: str) -> str:
        """Get ticket categories, prices, and seat availability for a specific event.
        Requires the event_id from search_events.

        Args:
            event_id: The event_id returned by search_events.
        """
        logger.info(f"[web:{self.user_id}] Executing Tool get_ticket_categories event_id={event_id}")
        res = await asyncio.to_thread(voice_db.get_ticket_categories, event_id)
        return res["message"]

    @function_tool
    async def book_ticket(self, event_id: str, category: str, seats: int) -> str:
        """Book tickets for the logged-in user for any supported event type.
Must collect event_id, category, and number of seats, then confirm
out loud before calling this.

Args:
    event_id: The event_id to book.
    category: Ticket category, e.g. 'VIP', 'Gold', 'Silver' — must match get_ticket_categories exactly.
    seats: Number of seats to book.
"""
        logger.info(f"[web:{self.user_id}] Executing Tool book_ticket event_id={event_id}, category={category}, seats={seats}")
        res = await asyncio.to_thread(voice_db.book_ticket_for_user, self.user_id, event_id, category, seats)
        return res["message"]

    @function_tool
    async def get_booking_status(self) -> str:
        """Check the status of the logged-in user's existing bookings."""
        logger.info(f"[web:{self.user_id}] Executing Tool get_booking_status")
        res = await asyncio.to_thread(voice_db.get_booking_status_for_user, self.user_id)
        return res["message"]

    @function_tool
    async def cancel_booking(self, booking_id: str) -> str:
        """Cancel one of the logged-in user's existing bookings. Must confirm the
        booking_id with them (from get_booking_status) before calling this.

        Args:
            booking_id: The booking_id to cancel.
        """
        logger.info(f"[web:{self.user_id}] Executing Tool cancel_booking booking_id={booking_id}")
        res = await asyncio.to_thread(voice_db.cancel_booking_for_user, self.user_id, booking_id)
        return res["message"]