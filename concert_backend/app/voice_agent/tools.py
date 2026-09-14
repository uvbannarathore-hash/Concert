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
from app.services.cancellation_service import get_cancellation_eligibility
from app.services.demand_service import get_buy_advice as _get_buy_advice
from app.agents.customer_tools import advise_seats as _advise_seats

logger = logging.getLogger("voice_tools")


def _format_eligibility(eligibility: dict) -> str:
    """Turns get_cancellation_eligibility()'s dict into one short spoken
    sentence - reused by both the phone and web toolsets so the refund
    breakdown is worded identically everywhere."""
    if not eligibility.get("eligible"):
        return eligibility.get("reason", "This booking cannot be cancelled.")
    return (
        f"This booking is eligible for cancellation. Eligible amount: INR {eligibility['eligible_amount']}. "
        f"Refund: {eligibility['refund_percentage']}% (INR {eligibility['refund_amount']}), "
        f"cancellation fee: {eligibility['cancellation_fee_percentage']}%. "
        f"Ask the caller/user to confirm before cancelling."
    )


def _format_buy_advice(advice: dict) -> str:
    if advice.get("error"):
        return advice["error"]
    return advice.get("message", "Demand information is not available for this event right now.")


def _format_seat_recommendations(result: dict) -> str:
    recs = result.get("recommendations")
    if not recs:
        return result.get("message", "No matching seats or tickets are available right now.")
    lines = []
    for r in recs[:5]:
        if isinstance(r, str):
            lines.append(r)
        elif isinstance(r, dict):
            lines.append(str(r))
    if not lines:
        return "No matching seats or tickets are available right now."
    return "Recommended options: " + "; ".join(lines)


def _split_seat_numbers(seat_numbers: str) -> list[str] | None:
    """Turns a spoken/typed list like 'N5, N6' or 'N 5 and N 6' into
    ['N5', 'N6']. Returns None if the string is empty (caller didn't
    specify seats, meaning the plain seats-count path should be used)."""
    if not seat_numbers or not seat_numbers.strip():
        return None
    raw = seat_numbers.replace(" and ", ",").replace(" ", "")
    return [s for s in raw.split(",") if s]


# Deterministic allow-list mapping a spoken/typed status word to the exact
# value voice_db.search_events' status_filter expects. Mirrors the "status"
# enum ["Upcoming", "Sold Out"] already exposed to Chat AI in
# app/agents/customer_tools.py's FUNCTION_DECLARATIONS - same two values,
# same meaning (leave unset to search both, like search_events' own
# default). Deliberately a fixed allow-list rather than passing the model's
# string straight through: it guarantees a model can never smuggle
# "Cancelled"/"Completed"/anything else into status_filter, regardless of
# how it's asked - no LLM-schema-enum reliance needed since Voice can run
# against providers (Groq/Ollama fallback) that don't enforce one as
# strictly as Gemini's structured output does.
_ALLOWED_STATUS_FILTERS = {"upcoming": "Upcoming", "sold out": "Sold Out", "soldout": "Sold Out"}


def _normalize_status_filter(status: str) -> str | None:
    """Returns the exact DB status value for a caller-facing status word,
    or None (meaning: no filter - voice_db.search_events' own default of
    Upcoming + Sold Out applies) for anything empty or not recognized."""
    if not status:
        return None
    return _ALLOWED_STATUS_FILTERS.get(status.strip().lower())


class ConcertBookingTools:
    """Tools exposed to the LLM agent for booking tickets for all supported event types over a phone call.

    caller_phone is bound here at construction time from the SIP participant's
    caller-ID-derived identity (see agent.py's entrypoint) - never taken from
    a model-supplied tool argument. This mirrors how ConcertBookingToolsWeb
    below binds user_id: the caller's identity must not be something the LLM
    can pick, guess, or override on a per-call basis, or a caller could ask
    the assistant to look up, cancel, or book against a phone number that
    isn't actually theirs."""

    def __init__(self, caller_phone: str):
        self.caller_phone = caller_phone

    @function_tool
    async def search_events(self, query: str = "", city: str = "", temporal_intent: str = "", specific_month: int = 0, status: str = "") -> str:
        """Search for upcoming events by artist name, city, and/or time period. Use this
        first to find the event_id before checking tickets or booking. Also use this for
        generic requests like 'what's upcoming' or 'any events tomorrow' - never answer
        from memory.

        Args:
            query: Artist or event name to search for, e.g. 'Arijit Singh'. Leave empty to just filter by city/time.
            city: City to filter by, e.g. 'Indore'. Optional.
            temporal_intent: Optional time filter. One of TODAY, TOMORROW, THIS_WEEK, THIS_WEEKEND, NEXT_WEEK, NEXT_WEEKEND, THIS_MONTH, NEXT_MONTH.
            specific_month: Optional specific month number (1-12), only if the caller names a specific month like 'December'.
            status: Optional. Pass 'Upcoming' if the caller specifically wants only events that are NOT sold out, or 'Sold Out' if they specifically ask which events are sold out (e.g. 'which events are sold out'). Leave empty otherwise - the default already includes both upcoming and sold-out events.
        """
        logger.info(f"Executing Tool search_events query={query}, city={city}, temporal_intent={temporal_intent}, specific_month={specific_month}, status={status}")
        res = await asyncio.to_thread(
            voice_db.search_events, query or None, city or None, temporal_intent or None, specific_month or None, _normalize_status_filter(status)
        )
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
        seats: int = 0,
        seat_numbers: str = "",
        caller_name: str = "",
    ) -> str:
        """Book tickets for the caller for any supported event type. Must collect event_id
        and category, and confirm out loud before calling this. For events with a seat map
        (has_seat_map=true from get_available_seats), ask which specific seats the caller
        wants and pass them as seat_numbers (e.g. 'N5, N6') - or if they say 'any 2 seats',
        pass seats as a plain count instead. For events without a seat map, always just use
        seats as a count.

        Args:
            event_id: The event_id to book.
            category: Ticket category, e.g. 'VIP', 'Gold', 'Silver' — must match get_ticket_categories exactly.
            seats: Number of seats to book - use this OR seat_numbers, not both.
            seat_numbers: Specific seats the caller chose, comma-separated e.g. 'N5, N6' - only for events with a seat map. Use this OR seats, not both.
            caller_name: The caller's name.
        """
        logger.info(
            f"Executing Tool book_ticket event_id={event_id}, category={category}, "
            f"seats={seats}, seat_numbers={seat_numbers}, phone={self.caller_phone}"
        )
        res = await asyncio.to_thread(
            voice_db.book_ticket,
            self.caller_phone,
            event_id,
            category,
            seats or None,
            _split_seat_numbers(seat_numbers),
            caller_name or None,
        )
        return res["message"]

    @function_tool
    async def get_booking_status(self, temporal_intent: str = "", specific_month: int = 0) -> str:
        """Check the status of the caller's own existing bookings, using the phone number
        this call is already identified by. Optionally filter by time period, e.g. 'this
        month' or 'in December'.

        Args:
            temporal_intent: Optional time filter. One of TODAY, TOMORROW, THIS_WEEK, THIS_WEEKEND, NEXT_WEEK, NEXT_WEEKEND, THIS_MONTH, NEXT_MONTH.
            specific_month: Optional specific month number (1-12), only if the caller names a specific month.
        """
        logger.info(f"Executing Tool get_booking_status phone={self.caller_phone}, temporal_intent={temporal_intent}, specific_month={specific_month}")
        res = await asyncio.to_thread(voice_db.get_booking_status, self.caller_phone, temporal_intent or None, specific_month or None)
        return res["message"]

    @function_tool
    async def check_cancellation_eligibility(self, booking_id: str) -> str:
        """Check whether one of the caller's own bookings can be cancelled and what the
        refund/fee breakdown would be. ALWAYS call this and read the refund amount to the
        caller, then get their explicit confirmation, BEFORE calling cancel_booking. Never
        invent cancellation policies or refund amounts.

        Args:
            booking_id: The booking_id to check.
        """
        logger.info(f"Executing Tool check_cancellation_eligibility phone={self.caller_phone}, booking_id={booking_id}")
        eligibility = await asyncio.to_thread(voice_db.check_cancellation_eligibility_for_phone, self.caller_phone, booking_id)
        return _format_eligibility(eligibility)

    @function_tool
    async def cancel_booking(self, booking_id: str) -> str:
        """Cancel one of the caller's own existing bookings. Only call this AFTER
        check_cancellation_eligibility was already called in this conversation and the
        caller has clearly confirmed (e.g. 'yes', 'confirm', 'cancel it') after hearing
        the refund breakdown. Automatically restores seats and initiates the Razorpay
        refund via the shared cancellation service. Never claim a refund is complete
        without checking the tool response.

        Args:
            booking_id: The booking_id to cancel.
        """
        logger.info(f"Executing Tool cancel_booking phone={self.caller_phone}, booking_id={booking_id}")
        res = await asyncio.to_thread(voice_db.cancel_booking, self.caller_phone, booking_id)
        return res["message"]

    @function_tool
    async def get_buy_advice(self, event_id: str) -> str:
        """Get the deterministic 'buy now vs wait' demand signal for a specific event -
        percent sold, days left, and urgency. Use for any demand/urgency question, e.g.
        'is this selling fast', 'should I buy now or wait', 'how many tickets are left',
        'is this in high demand', or 'are seats running out'. NEVER invent these metrics
        yourself.

        Args:
            event_id: The event ID (resolved from search_events).
        """
        logger.info(f"Executing Tool get_buy_advice event_id={event_id}")
        advice = await asyncio.to_thread(_get_buy_advice, event_id)
        return _format_buy_advice(advice)

    @function_tool
    async def advise_seats(
        self,
        event_id: str,
        max_price: float = 0,
        category: str = "",
        quantity: int = 1,
        preference: str = "",
    ) -> str:
        """Get deterministic seat or ticket-category recommendations for a specific
        event - cheapest, premium, N seats together, or a price limit. Use for requests
        like 'best seats', 'cheap seats', 'cheapest tickets', 'premium seats', 'seats
        under [price]', 'N seats together', 'best value', or 'which seats should I get'.
        Only returns seats that are actually available right now. Never invent seat
        numbers.

        Args:
            event_id: The event ID (resolved from search_events).
            max_price: Optional upper price filter (inclusive). 0 means no limit.
            category: Optional ticket category filter.
            quantity: Number of seats desired together (default 1).
            preference: Optional hint: 'cheap', 'best_value', or 'premium'.
        """
        logger.info(f"Executing Tool advise_seats event_id={event_id}, max_price={max_price}, category={category}, quantity={quantity}, preference={preference}")
        result = await asyncio.to_thread(
            _advise_seats, event_id, max_price or None, category or None, quantity or 1, preference or None
        )
        return _format_seat_recommendations(result)

    @function_tool
    async def get_user_hosted_shows(self) -> str:
        """Check the shows this caller has hosted or submitted themselves, using the phone
        number this call is already identified by. Never invent or infer this from
        conversation memory."""
        logger.info(f"Executing Tool get_user_hosted_shows phone={self.caller_phone}")
        res = await asyncio.to_thread(voice_db.get_user_hosted_shows_for_phone, self.caller_phone)
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
    async def search_events(self, query: str = "", city: str = "", temporal_intent: str = "", specific_month: int = 0, status: str = "") -> str:
        """Search for upcoming events by artist name, city, and/or time period. Use this
        first to find the event_id before checking tickets or booking. Also use this for
        generic requests like 'what's upcoming' or 'any events tomorrow' - never answer
        from memory.

        Args:
            query: Artist or event name to search for, e.g. 'Arijit Singh'. Leave empty to just filter by city/time.
            city: City to filter by, e.g. 'Indore'. Optional.
            temporal_intent: Optional time filter. One of TODAY, TOMORROW, THIS_WEEK, THIS_WEEKEND, NEXT_WEEK, NEXT_WEEKEND, THIS_MONTH, NEXT_MONTH.
            specific_month: Optional specific month number (1-12), only if the user names a specific month like 'December'.
            status: Optional. Pass 'Upcoming' if the user specifically wants only events that are NOT sold out, or 'Sold Out' if they specifically ask which events are sold out (e.g. 'which events are sold out'). Leave empty otherwise - the default already includes both upcoming and sold-out events.
        """
        logger.info(f"[web:{self.user_id}] Executing Tool search_events query={query}, city={city}, temporal_intent={temporal_intent}, specific_month={specific_month}, status={status}")
        res = await asyncio.to_thread(
            voice_db.search_events, query or None, city or None, temporal_intent or None, specific_month or None, _normalize_status_filter(status)
        )
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
    async def get_booking_status(self, temporal_intent: str = "", specific_month: int = 0) -> str:
        """Check the status of the logged-in user's existing bookings. Optionally filter
        by time period, e.g. 'this month' or 'in December'.

        Args:
            temporal_intent: Optional time filter. One of TODAY, TOMORROW, THIS_WEEK, THIS_WEEKEND, NEXT_WEEK, NEXT_WEEKEND, THIS_MONTH, NEXT_MONTH.
            specific_month: Optional specific month number (1-12), only if the user names a specific month.
        """
        logger.info(f"[web:{self.user_id}] Executing Tool get_booking_status temporal_intent={temporal_intent}, specific_month={specific_month}")
        res = await asyncio.to_thread(voice_db.get_booking_status_for_user, self.user_id, temporal_intent or None, specific_month or None)
        return res["message"]

    @function_tool
    async def check_cancellation_eligibility(self, booking_id: str) -> str:
        """Check whether a booking can be cancelled and what the refund/fee breakdown
        would be. ALWAYS call this and read the refund amount to the user, then get
        their explicit confirmation, BEFORE calling cancel_booking. Never invent
        cancellation policies or refund amounts.

        Args:
            booking_id: The booking_id to check.
        """
        logger.info(f"[web:{self.user_id}] Executing Tool check_cancellation_eligibility booking_id={booking_id}")
        eligibility = await asyncio.to_thread(get_cancellation_eligibility, booking_id, self.user_id)
        return _format_eligibility(eligibility)

    @function_tool
    async def cancel_booking(self, booking_id: str) -> str:
        """Cancel one of the logged-in user's existing bookings. Only call this AFTER
        check_cancellation_eligibility was already called in this conversation and the
        user has clearly confirmed (e.g. 'yes', 'confirm', 'cancel it') after hearing
        the refund breakdown. Automatically restores seats and initiates the Razorpay
        refund via the shared cancellation service. Never claim a refund is complete
        without checking the tool response.

        Args:
            booking_id: The booking_id to cancel.
        """
        logger.info(f"[web:{self.user_id}] Executing Tool cancel_booking booking_id={booking_id}")
        res = await asyncio.to_thread(voice_db.cancel_booking_for_user, self.user_id, booking_id)
        return res["message"]

    @function_tool
    async def get_buy_advice(self, event_id: str) -> str:
        """Get the deterministic 'buy now vs wait' demand signal for a specific event -
        percent sold, days left, and urgency. Use for any demand/urgency question, e.g.
        'is this selling fast', 'should I buy now or wait', 'how many tickets are left',
        'is this in high demand', or 'are seats running out'. NEVER invent these metrics
        yourself.

        Args:
            event_id: The event ID (resolved from search_events).
        """
        logger.info(f"[web:{self.user_id}] Executing Tool get_buy_advice event_id={event_id}")
        advice = await asyncio.to_thread(_get_buy_advice, event_id)
        return _format_buy_advice(advice)

    @function_tool
    async def advise_seats(
        self,
        event_id: str,
        max_price: float = 0,
        category: str = "",
        quantity: int = 1,
        preference: str = "",
    ) -> str:
        """Get deterministic seat or ticket-category recommendations for a specific
        event - cheapest, premium, N seats together, or a price limit. Use for requests
        like 'best seats', 'cheap seats', 'cheapest tickets', 'premium seats', 'seats
        under [price]', 'N seats together', 'best value', or 'which seats should I get'.
        Only returns seats that are actually available right now. Never invent seat
        numbers.

        Args:
            event_id: The event ID (resolved from search_events).
            max_price: Optional upper price filter (inclusive). 0 means no limit.
            category: Optional ticket category filter.
            quantity: Number of seats desired together (default 1).
            preference: Optional hint: 'cheap', 'best_value', or 'premium'.
        """
        logger.info(f"[web:{self.user_id}] Executing Tool advise_seats event_id={event_id}, max_price={max_price}, category={category}, quantity={quantity}, preference={preference}")
        result = await asyncio.to_thread(
            _advise_seats, event_id, max_price or None, category or None, quantity or 1, preference or None
        )
        return _format_seat_recommendations(result)

    @function_tool
    async def get_user_hosted_shows(self) -> str:
        """Check the shows the logged-in user has hosted or submitted themselves. Never
        invent or infer this from conversation memory."""
        logger.info(f"[web:{self.user_id}] Executing Tool get_user_hosted_shows")
        res = await asyncio.to_thread(voice_db.get_user_hosted_shows, self.user_id)
        return res["message"]