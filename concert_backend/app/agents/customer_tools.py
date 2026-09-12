"""
customer_tools.py — Tools for the customer-facing AI assistant (website chat
+ Telegram), ported from the n8n "Concert Ticket Booking Assistant"
workflow.

Most of the booking-related logic here is NOT reimplemented - it already
exists natively in app/voice_agent/voice_db.py (written for the phone voice
agent), and that logic is identical to what the n8n workflow's
book_ticket_transaction/get_user_booking_history/cancel_booking tools did
(same book_ticket_transaction RPC, same tables, same rules). We just import
and reuse those functions directly instead of re-implementing them.

The one genuinely new tool is link_telegram_account, which calls the
link_telegram_account Postgres RPC the n8n workflow already relied on (if
that RPC doesn't exist in your database yet, see the accompanying migration
notes).

check_events_availability from n8n was a single generic tool that let the
AI construct raw PostgREST filter strings against any of 3 tables - that's
more power (and more injection-style risk) than needed here. We split it
into two safe, specific tools instead (search_events, get_ticket_categories)
- both already exist in voice_db.py, reused as-is.

Note: book_ticket_transaction, get_user_booking_history, and cancel_booking
all need to know WHICH user is chatting. That user_id is resolved once per
request (website: from the authenticated JWT; Telegram: from the chat's
linked/auto-created profile - see customer_agent.py) and is NEVER something
the AI should ask for, guess, or be allowed to override. So these tools are
defined here as functions that take user_id explicitly, and
customer_agent.py builds per-request handler closures that bind the
resolved user_id before handing them to the Gemini loop - the AI's function
declarations below deliberately do NOT expose a user_id parameter at all.
"""

from app.supabase_client import supabase_admin
from app.voice_agent import voice_db


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def search_events(query: str = None, city: str = None, temporal_intent: str = None, specific_month: int = None, status: str = None) -> dict:
    return voice_db.search_events(query, city, temporal_intent, specific_month, status)


def get_ticket_categories(event_id: str) -> dict:
    return voice_db.get_ticket_categories(event_id)


def get_available_seats(event_id: str, category: str = None) -> dict:
    return voice_db.get_available_seats(event_id, category)


def book_ticket_transaction(user_id: str, event_id: str, category: str, seats: int = None,
                             seat_numbers: list = None, source: str = "website") -> dict:
    return voice_db.book_ticket_for_user(user_id, event_id, category, seats=seats, seat_numbers=seat_numbers, source=source)


def get_user_booking_history(user_id: str, temporal_intent: str = None, specific_month: int = None) -> dict:
    return voice_db.get_booking_status_for_user(user_id, temporal_intent, specific_month)

def get_buy_advice(event_id: str) -> dict:
    from app.services.demand_service import get_buy_advice as service_get_buy_advice
    return service_get_buy_advice(event_id)

def get_user_hosted_shows(user_id: str) -> dict:
    return voice_db.get_user_hosted_shows(user_id)


def cancel_booking(user_id: str, booking_id: str) -> dict:
    return voice_db.cancel_booking_for_user(user_id, booking_id)


def link_telegram_account(chat_id: str, email: str) -> dict:
    """Links a Telegram chat to an existing website account by email, via
    the link_telegram_account RPC. chat_id is bound from the resolved
    request context (see customer_agent.py), never provided by the AI."""
    if not chat_id:
        return {"linked": False, "message": "Account linking is only available in Telegram conversations."}

    result = supabase_admin.rpc(
        "link_telegram_account", {"p_chat_id": chat_id, "p_email": email}
    ).execute()
    return result.data


# ---------------------------------------------------------------------------
# Gemini function declarations (JSON schema)
#
# Deliberately no user_id/chat_id parameter on any of these - customer_agent.py
# binds those from the resolved request context, not from the model.
# ---------------------------------------------------------------------------

FUNCTION_DECLARATIONS = [
    {
        "name": "search_events",
        "description": "Use this for upcoming events, concert dates, event locations, ticket "
        "availability, prices, or categories. Use it for any 'which concerts/events are "
        "available', 'show me X concerts', or 'when is the next X' question.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Artist or event name to search for, e.g. 'Arijit Singh'. Leave empty to just filter by city."},
                "city": {"type": "string", "description": "City to filter by, e.g. 'Mumbai'. Optional."},
                "temporal_intent": {
                    "type": "string",
                    "description": "Optional temporal constraint inferred from the user query.",
                    "enum": ["TODAY", "TOMORROW", "THIS_WEEK", "THIS_WEEKEND", "NEXT_WEEK", "NEXT_WEEKEND", "THIS_MONTH", "NEXT_MONTH", "ALL"]
                },
                "specific_month": {
                    "type": "integer",
                    "description": "Optional specific month number (1-12) if the user asks for a specific month like 'December'. Only use if a specific month is named."
                },
                "status": {
                    "type": "string",
                    "description": "Optional status filter. If the user explicitly asks for 'Sold Out' concerts, pass 'Sold Out'. Otherwise, leave empty to search upcoming available events.",
                    "enum": ["Upcoming", "Sold Out"]
                }
            },
        },
    },
    {
        "name": "get_ticket_categories",
        "description": "Use this to get ticket categories, prices, and seat availability for a "
        "specific event. Requires the event_id from search_events.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event_id returned by search_events."},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "get_available_seats",
        "description": "Use this AFTER get_ticket_categories, before booking, for events that use "
        "seat selection (an interactive seat map, like a cinema or stadium). Returns exactly which "
        "seats (row + number) are currently open in a category, e.g. 'Row N: 1, 2, 5, 8'. If the "
        "result says has_seat_map is false, this event does NOT use seat selection - just ask how "
        "many tickets the user wants instead of asking for seat numbers. Call this whenever the "
        "user wants to see or choose specific seats, or before confirming a booking so you can "
        "mention what's actually available.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event_id to check seats for."},
                "category": {"type": "string", "description": "Optional - limit results to one ticket category."},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "book_ticket_transaction",
        "description": "Starts the ticket booking process. NEVER use this before the user "
        "explicitly confirms the booking (e.g. 'Yes, proceed', 'Confirm', 'Book it'). NEVER call "
        "this just because the user said 'Book 2 VIP tickets' - first show the complete booking "
        "summary and ask for confirmation. This checks availability, reserves seats, creates the "
        "booking as Pending Payment, and returns a Razorpay payment link. This does NOT instantly "
        "confirm the booking - you must send the payment_link to the user and clearly tell them "
        "the booking is reserved but only confirmed once they complete payment. NEVER claim a "
        "booking is confirmed - only that it's reserved pending payment.\n\n"
        "SEATS: for events where get_available_seats returned has_seat_map=true, ask the user "
        "which specific seats they want (e.g. 'N5, N6') and pass them as seat_numbers - or if they "
        "say 'any 2 seats' / don't care which, pass seats as a plain count instead and the system "
        "will auto-pick available ones. For events where has_seat_map=false (or you haven't checked "
        "seats at all), just pass seats as a count - never pass seat_numbers for those events.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event_id of the concert being booked."},
                "category": {"type": "string", "description": "The ticket category, must match get_ticket_categories exactly."},
                "seats": {"type": "integer", "description": "Number of seats to book - use this OR seat_numbers, not both. Required if not using seat_numbers."},
                "seat_numbers": {
                    "type": "array",
                    "description": "Specific seats the user chose, e.g. ['N5', 'N6'] - only for events with has_seat_map=true. Use this OR seats, not both.",
                    "items": {"type": "string"},
                },
            },
            "required": ["event_id", "category"],
        },
    },
    {
        "name": "get_user_booking_history",
        "description": "The source of truth for the user's own previous bookings and booking "
        "history. Use this whenever the user asks about previous bookings, booking history, what "
        "they booked before, or their past concerts. NEVER answer these from conversation memory "
        "- always use this tool. The tool response will tell you the exact total count of matching bookings. Never infer the total count just by looking at the returned array, use the total_count field.",
        "parameters": {
            "type": "object", 
            "properties": {
                "temporal_intent": {
                    "type": "string",
                    "description": "Optional temporal constraint inferred from the user query.",
                    "enum": ["TODAY", "TOMORROW", "THIS_WEEK", "THIS_WEEKEND", "NEXT_WEEK", "NEXT_WEEKEND", "THIS_MONTH", "NEXT_MONTH", "ALL"]
                },
                "specific_month": {
                    "type": "integer",
                    "description": "Optional specific month number (1-12) if the user asks for a specific month like 'December'. Only use if a specific month is named."
                }
            }
        },
    },
    {
        "name": "get_user_hosted_shows",
        "description": "Use this whenever the user asks about shows they have hosted, submitted, or listed. "
        "This tool is the source of truth for the user's own hosted/submitted shows. NEVER invent or infer "
        "this from conversation memory.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "cancel_booking",
        "description": "Use this ONLY when the user explicitly wants to cancel an existing "
        "booking. If the booking_id is not known, first call get_user_booking_history to find it, "
        "then confirm with the user which booking to cancel. Always get explicit confirmation "
        "before finalizing the cancellation.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "string", "description": "The booking ID to cancel."},
            },
            "required": ["booking_id"],
        },
    },
    {
        "name": "link_telegram_account",
        "description": "Links this Telegram chat to an existing website account so the user's "
        "bookings, wishlist, and preferences carry over here. ONLY use this when the user "
        "explicitly provides the email address they signed up with on the website, and only in a "
        "Telegram conversation. Never guess or reuse an email from earlier in the conversation "
        "without the user confirming it's the right one for this purpose. Returns linked: true on "
        "success, or linked: false with a message if no account matched that email.",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "The email address the user signed up with on the website."},
            },
            "required": ["email"],
        },
    },
    {
        "name": "get_buy_advice",
        "description": "Use this to get the deterministic 'buy now vs wait' demand signal for a specific event. Returns % sold, days left, and urgency level. NEVER invent these metrics yourself.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID."},
            },
            "required": ["event_id"],
        },
    },
]

# ---------------------------------------------------------------------------
# Tool handler registry
# ---------------------------------------------------------------------------

TOOL_HANDLERS = {
    "search_events": search_events,
    "get_ticket_categories": get_ticket_categories,
    "get_available_seats": get_available_seats,
    "book_ticket_transaction": book_ticket_transaction,
    "get_user_booking_history": get_user_booking_history,
    "get_user_hosted_shows": get_user_hosted_shows,
    "cancel_booking": cancel_booking,
    "link_telegram_account": link_telegram_account,
    "get_buy_advice": get_buy_advice,
}