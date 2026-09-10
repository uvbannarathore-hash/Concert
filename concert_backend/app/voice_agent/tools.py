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


def _split_seat_numbers(seat_numbers: str) -> list[str] | None:
    """Turns a spoken/typed list like 'N5, N6' or 'N 5 and N 6' into
    ['N5', 'N6']. Returns None if the string is empty (caller didn't
    specify seats, meaning the plain seats-count path should be used)."""
    if not seat_numbers or not seat_numbers.strip():
        return None
    raw = seat_numbers.replace(" and ", ",").replace(" ", "")
    return [s for s in raw.split(",") if s]


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
    async def get_available_seats(self, event_id: str, category: str = "") -> str:
        """Use this AFTER get_ticket_categories, before booking, for events with an
        interactive seat map (a cinema/stadium with named seats like N5). Tells you
        exactly which seats are open, row by row. If the result says this event doesn't
        use seat selection, just ask the caller how many tickets they want instead of
        asking for seat numbers.

        Args:
            event_id: The event_id to check seats for.
            category: Optional - limit results to one ticket category.
        """
        logger.info(f"Executing Tool get_available_seats event_id={event_id}, category={category}")
        res = await asyncio.to_thread(voice_db.get_available_seats, event_id, category or None)
        return res["message"]

    @function_tool
    async def book_ticket(
        self,
        event_id: str,
        category: str,
        caller_phone: str,
        seats: int = 0,
        seat_numbers: str = "",
        caller_name: str = "",
    ) -> str:
        """Book tickets for the caller for any supported event type. Must collect event_id,
        category, and confirm the caller's phone number and name before calling this. For
        events with a seat map (has_seat_map=true from get_available_seats), ask which
        specific seats the caller wants and pass them as seat_numbers (e.g. 'N5, N6') - or
        if they say 'any 2 seats', pass seats as a plain count instead. For events without
        a seat map, always just use seats as a count.

        Args:
            event_id: The event_id to book.
            category: Ticket category, e.g. 'VIP', 'Gold', 'Silver' — must match get_ticket_categories exactly.
            caller_phone: The caller's phone number (from caller ID or confirmed verbally).
            seats: Number of seats to book - use this OR seat_numbers, not both.
            seat_numbers: Specific seats the caller chose, comma-separated e.g. 'N5, N6' - only for events with a seat map. Use this OR seats, not both.
            caller_name: The caller's name.
        """
        logger.info(
            f"Executing Tool book_ticket event_id={event_id}, category={category}, "
            f"seats={seats}, seat_numbers={seat_numbers}, phone={caller_phone}"
        )
        res = await asyncio.to_thread(
            voice_db.book_ticket,
            caller_phone,
            event_id,
            category,
            seats or None,
            _split_seat_numbers(seat_numbers),
            caller_name or None,
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
    async def get_available_seats(self, event_id: str, category: str = "") -> str:
        """Use this AFTER get_ticket_categories, before booking, for events with an
        interactive seat map (a cinema/stadium with named seats like N5). Tells you
        exactly which seats are open, row by row. If the result says this event doesn't
        use seat selection, just ask how many tickets instead of asking for seat numbers.

        Args:
            event_id: The event_id to check seats for.
            category: Optional - limit results to one ticket category.
        """
        logger.info(f"[web:{self.user_id}] Executing Tool get_available_seats event_id={event_id}, category={category}")
        res = await asyncio.to_thread(voice_db.get_available_seats, event_id, category or None)
        return res["message"]

    @function_tool
    async def book_ticket(self, event_id: str, category: str, seats: int = 0, seat_numbers: str = "") -> str:
        """Book tickets for the logged-in user for any supported event type. Must collect
        event_id and category, then confirm out loud before calling this. For events with
        a seat map (has_seat_map=true from get_available_seats), ask which specific seats
        the user wants and pass them as seat_numbers (e.g. 'N5, N6') - or if they say 'any
        2 seats', pass seats as a plain count instead. For events without a seat map,
        always just use seats as a count.

        Args:
            event_id: The event_id to book.
            category: Ticket category, e.g. 'VIP', 'Gold', 'Silver' — must match get_ticket_categories exactly.
            seats: Number of seats to book - use this OR seat_numbers, not both.
            seat_numbers: Specific seats the user chose, comma-separated e.g. 'N5, N6' - only for events with a seat map. Use this OR seats, not both.
        """
        logger.info(
            f"[web:{self.user_id}] Executing Tool book_ticket event_id={event_id}, "
            f"category={category}, seats={seats}, seat_numbers={seat_numbers}"
        )
        res = await asyncio.to_thread(
            voice_db.book_ticket_for_user,
            self.user_id,
            event_id,
            category,
            seats or None,
            _split_seat_numbers(seat_numbers),
        )
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