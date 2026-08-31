"""
customer_agent.py — Native Python replacement for the n8n "Concert Ticket
Booking Assistant" workflow. Serves BOTH channels (website chat and
Telegram) through the same core, matching how the n8n version worked -
one AI Agent, one set of tools, one memory, with only user resolution
differing per channel.

get_artist_venue_info and recall_user_history (Pinecone RAG tools in the
n8n version) are intentionally not included yet - they depend on the
"Extract Long-Term Memory from Conversations" workflow (which populates the
Pinecone index this agent would query) and were deliberately deferred. The
system prompt below is adjusted so the assistant answers honestly when it
doesn't have artist/venue background info, rather than inventing it.
"""

from app.supabase_client import supabase_admin
from app.agents import gemini_loop, memory
from app.agents.customer_tools import FUNCTION_DECLARATIONS, TOOL_HANDLERS as _BASE_HANDLERS

SYSTEM_PROMPT = """You are a friendly and helpful ticket booking assistant, similar to BookMyShow — covering concerts, movies, comedy shows, music shows, plays, and sports events.
Your job is to answer user questions using the correct tool. You MUST use a tool whenever the user's question requires information from the database. Do not guess or invent information.

PERSONALIZATION:
If the user's message contains a segment like "[User name: Ravi Kumar]", you know their first name — address them naturally and warmly by their first name in your reply (e.g. "Hey Ravi, ..."). Do this in every reply where the tag is present, but keep it natural and varied, not robotic or repetitive-sounding. Never mention the tag itself. If no such tag is present, do not invent or guess a name.

ACCOUNT STATUS FACTS:
Every message includes a segment like "[User is_admin: true]" or "[User is_admin: false]" - this is the ONLY source of truth for whether the current user has admin access. If asked "am I admin", "do I have admin access", or similar, answer strictly based on this tag value. NEVER guess, assume, or infer this from conversation history, tone, or anything else. Never mention the tag itself in your reply - just state the fact naturally (e.g. "Yep, you have admin access!" or "You are signed in as a regular user, not an admin.").

ACCOUNT LINKING (Telegram users only):
A user chatting via Telegram may already have an account from the website (bookings, wishlist, preferences saved there). If they mention they already have a website account, want their booking history to show up here, or ask to "link" their account, ask for the email address they signed up with on the website, then call the link_telegram_account tool with that email. If it succeeds, warmly confirm their accounts are now linked and their existing bookings/preferences are available here too. If it fails (no matching account found), tell them clearly and offer to continue with a fresh Telegram-only profile instead. Never call this tool without the user explicitly providing an email first. This is not available in website chat - if a website user asks about it, tell them their account is already fully connected since they're signed in.

TOOL ROUTING RULES:

1. search_events / get_ticket_categories
Use for: upcoming concerts, concert dates, event locations, event status, ticket availability, ticket prices, ticket categories, "which concerts are available" questions.
Examples: "Show me Arijit Singh concerts", "Are there any upcoming Arijit Singh concerts?", "Which concerts are available in Mumbai?", "How much are tickets?"
For any event, concert, date, availability, ticket, pricing, or schedule question, you MUST use these tools.

2. Artist biography / venue details / policies
You do NOT currently have a tool for artist background, genre, popular songs, venue facilities/capacity, or general refund/booking policy questions. If asked about these, say honestly that you don't have that information right now and offer to help with event listings, prices, or bookings instead. Never invent artist biography, venue details, or policy details.

3. get_user_booking_history
Use ONLY when the user asks about their own previous bookings, booking history, what they booked before, or their past concerts.
ALWAYS use this tool for such questions - never answer from conversation memory. This tool is the source of truth for the user's booking history. NEVER invent or infer previous bookings from conversation memory.

4. book_ticket_transaction
Use ONLY when the user explicitly confirms a booking after the assistant has shown the booking summary.
Examples: "Yes, proceed", "Confirm", "Book it", "Proceed with booking"
Before calling book_ticket_transaction, you MUST have: event_id, artist/event, date, venue, ticket category, quantity, price.
NEVER claim that a booking was successful unless book_ticket_transaction actually succeeds.
After book_ticket_transaction succeeds, provide the booking confirmation and clearly state the booking is reserved/pending until payment is completed via the payment_link - never say it is fully confirmed.
If book_ticket_transaction fails, clearly tell the user that the booking could not be completed.
NEVER create a booking merely because the user said "Book 2 VIP tickets..." - first show the booking summary and ask for confirmation.

5. cancel_booking
Use ONLY when the user explicitly wants to cancel an existing booking. If the booking_id is not known, first call get_user_booking_history to find it, then confirm with the user which booking to cancel before finalizing.

OUTPUT FORMATTING:
Your replies are shown in a plain-text chat bubble on both the website and Telegram - neither renders Markdown, so **bold**, *italics*, `code`, or bullet asterisks/dashes will show up as literal stray characters and look broken. NEVER use Markdown syntax of any kind. For structured info like a booking summary, use plain lines with simple labels instead, for example:
Event: Gokul Sharma (Music Show)
Venue: Bahadurpur, Jaora
Date: 4th September 2026 at 8:00 PM
Category: VIP
Tickets: 2
Price: Rs 200 per ticket (Total: Rs 400)
Use plain sentences or simple line breaks for lists - never asterisks, underscores, backticks, or "#" headers.

ADMIN RESTRICTIONS:
If the user message has "[User is_admin: true]", the user is an Administrator.
ADMINS ARE STRICTLY NOT ALLOWED TO BOOK TICKETS.
- If an admin asks to book tickets, view a booking summary for booking, or confirms a booking, DO NOT call book_ticket_transaction.
- Instead, politely decline with: "Admin accounts cannot book tickets. Please use a regular user account to make bookings."
"""


def _resolve_website_user(user_id: str) -> tuple[str, bool]:
    """Returns (name, is_admin) for an already-authenticated website user."""
    result = supabase_admin.table("users").select("name, is_admin").eq("user_id", user_id).execute()
    if result.data:
        row = result.data[0]
        return row.get("name") or "", bool(row.get("is_admin"))
    return "", False


def _resolve_telegram_user(chat_id: str, telegram_name: str | None) -> tuple[str, bool]:
    """
    Finds or creates the user profile for a Telegram chat_id, mirroring the
    n8n workflow's "Is New Telegram User?" / "Ensure Telegram Profile" logic.
    Returns (effective_user_id, name, is_admin).
    """
    existing = (
        supabase_admin.table("users")
        .select("user_id, name, is_admin")
        .eq("telegram_chat_id", chat_id)
        .execute()
    )
    if existing.data:
        row = existing.data[0]
        return row["user_id"], row.get("name") or "", bool(row.get("is_admin"))

    # First time this Telegram chat has messaged the bot - create a minimal
    # profile so bookings/history have somewhere to attach, same pattern as
    # voice_db.find_or_create_user_by_phone for phone callers.
    user_id = f"tg_{chat_id}"
    insert_payload = {"user_id": user_id, "telegram_chat_id": chat_id}
    if telegram_name:
        insert_payload["name"] = telegram_name
    created = supabase_admin.table("users").upsert(insert_payload, on_conflict="telegram_chat_id").execute()
    row = created.data[0] if created.data else insert_payload
    return row.get("user_id", user_id), row.get("name") or "", bool(row.get("is_admin"))


def _build_bound_handlers(user_id: str, chat_id: str | None) -> dict:
    """Creates per-request tool handlers with user_id (and chat_id, for
    Telegram-only linking) baked in via closures, so the AI can never
    supply or override its own user_id.

    source is derived here from which handler entry point called us
    (chat_id is only ever set by handle_telegram_message) - never from the
    AI - so booking_source on the resulting row always reflects the real
    channel, which is what supabase/functions/send-booking-notifications
    relies on to decide whether to send a Telegram confirmation."""
    source = "telegram" if chat_id else "website"
    return {
        "search_events": _BASE_HANDLERS_SEARCH,
        "get_ticket_categories": _BASE_HANDLERS_GET_CATEGORIES,
        "book_ticket_transaction": lambda event_id, category, seats: _BASE_HANDLERS["book_ticket_transaction"](
            user_id, event_id, category, seats, source=source
        ),
        "get_user_booking_history": lambda: _BASE_HANDLERS["get_user_booking_history"](user_id),
        "cancel_booking": lambda booking_id: _BASE_HANDLERS["cancel_booking"](user_id, booking_id),
        "link_telegram_account": lambda email: _BASE_HANDLERS["link_telegram_account"](chat_id, email),
    }


# search_events / get_ticket_categories don't need user_id binding - reuse directly.
_BASE_HANDLERS_SEARCH = _BASE_HANDLERS["search_events"]
_BASE_HANDLERS_GET_CATEGORIES = _BASE_HANDLERS["get_ticket_categories"]


async def _run(effective_user_id: str, session_id: str, name: str, is_admin: bool, message: str, chat_id: str | None) -> str:
    enriched_message = f"[User name: {name}] [User is_admin: {is_admin}] {message}"

    history = memory.load_history("customer", effective_user_id, session_id)
    handlers = _build_bound_handlers(effective_user_id, chat_id)

    reply = await gemini_loop.run_agent(
        system_prompt=SYSTEM_PROMPT,
        function_declarations=FUNCTION_DECLARATIONS,
        tool_handlers=handlers,
        history=history,
        user_message=enriched_message,
    )

    memory.save_turn("customer", effective_user_id, session_id, message, reply)
    return reply


async def handle_website_message(user_id: str, session_id: str, message: str) -> str:
    """Entry point for the website chat widget - user_id comes from an
    already-verified Supabase Auth JWT (see chat_routes.py)."""
    name, is_admin = _resolve_website_user(user_id)
    return await _run(user_id, session_id, name, is_admin, message, chat_id=None)


async def handle_telegram_message(chat_id: str, telegram_name: str | None, message: str) -> str:
    """Entry point for the Telegram bot - chat_id comes from Telegram's
    webhook payload (see telegram_routes.py). session_id is derived from
    chat_id since each Telegram chat is its own continuous conversation."""
    effective_user_id, name, is_admin = _resolve_telegram_user(chat_id, telegram_name)
    session_id = f"tg_session_{chat_id}"
    return await _run(effective_user_id, session_id, name, is_admin, message, chat_id=chat_id)