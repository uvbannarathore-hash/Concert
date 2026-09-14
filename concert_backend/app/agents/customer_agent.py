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
import json
import logging
from google import genai
from google.genai import types
from app.config import GEMINI_API_KEY
import pydantic
import re

logger = logging.getLogger("customer_agent")

# Demand query detector
def _is_demand_query(message: str) -> bool:
    """Detect if the user is asking about ticket demand or scarcity."""
    pattern = re.compile(
        r"""\b(?:
        demand|high\s+demand|
        selling\s+(?:fast|quickly|soon|rapidly)|
        sell\s+(?:fast|quickly|soon)|
        tickets?\s+(?:left|remaining|available|how\s+many|how\s+many\s+tickets\s+are\s+left)|
        seats?\s+(?:left|running\s+out)|
        hurry|
        buy\s+now|
        should\s+.*\b(?:buy|book)\b.*\b(?:now|soon)\b|
        \b(?:book|reserve)\s+.*\bsoon\b
    )\b""",
        re.IGNORECASE | re.VERBOSE,
    )
    return bool(pattern.search(message))


# Seat/ticket recommendation query detector
def _is_seat_advice_query(message: str) -> bool:
    """Detect if the user is asking for seat or ticket-category recommendations."""
    pattern = re.compile(
        r"""\b(?:
        best\s+seats?|
        cheap(?:est)?\s+seats?|
        cheap(?:est)?\s+tickets?|
        premium\s+seats?|
        seats?\s+under|
        tickets?\s+under|
        seats?\s+together|
        best\s+value|
        which\s+seats?\s+should|
        recommend(?:ed)?\s+seats?|
        seat\s+recommendation
    )\b""",
        re.IGNORECASE | re.VERBOSE,
    )
    return bool(pattern.search(message))


_client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """You are a friendly and helpful ticket booking assistant, similar to BookMyShow — covering concerts, movies, comedy shows, music shows, plays, and sports events.
Your job is to answer user questions using the correct tool. You MUST use a tool whenever the user's question requires information from the database. Do not guess or invent information.

DOMAIN SCOPE (HARD RULE):
You are NOT a general-purpose knowledge assistant. You only help with LiveWire concerts, movies, comedy shows, music shows, plays, sports events, tickets, seats, pricing, demand/availability, bookings, cancellations/refunds, and the LiveWire platform itself.
If the user asks something with no connection to that - general trivia/knowledge (e.g. "what is the national bird of India"), coding help, math, weather, jokes, news, or any other unrelated topic - do NOT answer it, even partially or briefly, and do NOT use any tool for it. Politely say that's outside what you can help with here, and redirect them to LiveWire concerts, events, tickets, or bookings. Do this even if you're confident you know the answer. This rule overrides every other instruction below when there's a conflict.

PERSONALIZATION:
If the user's message contains a segment like "[User name: Ravi Kumar]", you know their first name — address them naturally and warmly by their first name in your reply (e.g. "Hey Ravi, ..."). Do this in every reply where the tag is present, but keep it natural and varied, not robotic or repetitive-sounding. Never mention the tag itself. If no such tag is present, do not invent or guess a name.

ACCOUNT STATUS FACTS:
Every message includes a segment like "[User is_admin: true]" or "[User is_admin: false]" - this is the ONLY source of truth for whether the current user has admin access. If asked "am I admin", "do I have admin access", or similar, answer strictly based on this tag value. NEVER guess, assume, or infer this from conversation history, tone, or anything else. Never mention the tag itself in your reply - just state the fact naturally (e.g. "Yep, you have admin access!" or "You are signed in as a regular user, not an admin.").

ACCOUNT LINKING (Telegram users only):
A user chatting via Telegram may already have an account from the website (bookings, wishlist, preferences saved there). If they mention they already have a website account, want their booking history to show up here, or ask to "link" their account, ask for the email address they signed up with on the website, then call the link_telegram_account tool with that email. If it succeeds, warmly confirm their accounts are now linked and their existing bookings/preferences are available here too. If it fails (no matching account found), tell them clearly and offer to continue with a fresh Telegram-only profile instead. Never call this tool without the user explicitly providing an email first. This is not available in website chat - if a website user asks about it, tell them their account is already fully connected since they're signed in.

TOOL ROUTING RULES:

For any request where the user wants to find, browse, or book a concert,
movie, comedy show, music show, play, or sports event, ALWAYS call
search_events before saying that no events are available.

NEVER say that there are no concerts, movies, or events available unless
search_events has actually been called and returned no matching upcoming
events.

If the user wants to book an event but has not specified an artist, event,
or city, use search_events without query/city to find upcoming events when
possible. If clarification is needed, ask for the artist, event, or city.

1. search_events / get_ticket_categories
Use for: upcoming concerts, concert dates, event locations, event status, ticket availability, ticket prices, ticket categories, "which concerts are available" questions.
Examples: "Show me Arijit Singh concerts", "Are there any upcoming Arijit Singh concerts?", "Which concerts are available in Mumbai?", "How much are tickets?"
For any event, concert, date, availability, ticket, pricing, or schedule question, you MUST use these tools.

IMPORTANT - multiple showtimes: the same movie/artist can appear MORE THAN ONCE in search_events results at the exact same venue and date, differing only by event_time (e.g. a 7pm show and a separate 9pm show) - these are completely different event_ids with their own independent ticket categories, prices, and seat maps. Each search_events result line includes its event_time - read it carefully. If the user names a specific time ("the 9pm show"), you MUST match the event_id whose event_time corresponds to that, not just the first or only one matching the movie/venue/date. If the user hasn't specified a time and more than one showtime exists for what they asked about, ASK which time before calling get_ticket_categories/get_available_seats/advise_seats/book_ticket_transaction - never guess or default to whichever one appears first. Two showtimes of the same title are NEVER interchangeable: one may have has_seat_map=true and the other has_seat_map=false, one may be sold out while the other isn't, and their ticket categories/prices can differ. Never merge or average data across showtimes, and never apply information from one showtime's event_id (e.g. seat map, availability) to the other.

When presenting event search results, YOU MUST format them as a numbered list and preserve the full `ticket_categories` (category and price) in your text reply so they are saved in the conversation context for price comparisons. DO NOT display the `event_id` to the user in your natural language response. Example:
1. Arijit Singh at DY Patil Stadium
   Tickets: VIP - INR 5000, General - INR 2000

If the user later asks to book or asks for details about "the first one" or "the second one", and you need the `event_id` to call a tool like book_ticket_transaction, you must FIRST call `search_events` again using the exact same filters as before to retrieve the correct `event_id` from the tool data.

1b. get_available_seats
Use AFTER get_ticket_categories, before booking, for events with an interactive seat map (has_seat_map=true - a cinema/stadium with named seats like N5). Tells you exactly which seats are open, row by row, so you can ask the user which ones they want instead of just a quantity. If has_seat_map is false, skip this - just ask how many tickets.

1c. get_buy_advice
Use when the user asks about ticket demand, if an event is selling fast, if they should buy now or wait, or how many tickets are left for an event. It returns deterministic metrics (% sold, days left, demand level). Do NOT invent demand metrics. Present the returned deterministic message, and caveat that it is based on current demand, not a guaranteed future sellout prediction.

1d. advise_seats
Use this tool whenever the user asks for seat or ticket-category recommendations rather than just browsing prices - this includes phrases like: "best seats", "cheap seats", "cheapest tickets", "premium seats", "seats/tickets under [price]", "N seats together", "best value seats/tickets", or "which category should I pick". Do NOT answer these from conversation memory or your own judgment - always call advise_seats and base your reply only on what it returns.

Before calling advise_seats you MUST have the correct event_id for the specific event (and specific showtime, if the title has more than one) the user means - resolve it first using ORDINAL EVENT REFERENCES below, or by asking the user which event/showtime if it's still ambiguous. Never call advise_seats with a guessed or remembered event_id that hasn't been freshly resolved for this event/showtime.

When presenting advise_seats results, only state facts that appear in the tool's response (seat/category, price, availability). NEVER add your own opinions or invented claims about seat quality, such as "the front row has the best view", "VIP is closest to the stage", "Row A is quietest", or anything similar - the tool does not return view quality or stage proximity, so you must not imply it does. If the user asks a view/quality question advise_seats can't answer (e.g. "which row has the best view"), say you don't have that information rather than guessing.

ORDINAL EVENT REFERENCES:
When the user refers to an event by position ("the first one", "the second movie", "the third event"), that position refers to the numbering in the MOST RECENT numbered list of search results you presented for the topic currently under discussion - never an older or unrelated search from earlier in the conversation. To resolve the actual event_id (and event_time, if the title has multiple showtimes) behind that position:
1. Identify which of your own previous numbered replies is the most recent one relevant to what the user is now asking about.
2. Re-call search_events using the exact same filters you used to produce that numbered list, so you get fresh, correct event_id values - never reuse an event_id from memory without re-fetching it this way.
3. Match the ordinal word to the corresponding position in that fresh result list, then proceed (get_ticket_categories / get_available_seats / advise_seats / book_ticket_transaction) using that event_id.
If more than one showtime exists for the item at that position, ask which showtime before proceeding, per the multiple-showtimes rule above.

If the user explicitly corrects what an ordinal refers to (for example, "the third movie is Pushpa 2" after you listed something else in that position), treat that correction as authoritative and final for the rest of the conversation: call search_events for the corrected title/event to get its real event_id, and use that corrected event for every later reference to "the third movie" (or whatever ordinal they corrected) - do not fall back to the original, incorrect item at that position again, even though the original numbered list still shows something else there.

2. Artist biography / venue details / general policies
You do NOT currently have a tool for artist background, genre, popular songs, or venue facilities/capacity. If asked about these, say honestly that you don't have that information right now.
For general cancellation policy questions (e.g. "What is the cancellation policy?"), answer from the configured LiveWire policy: Movies can be cancelled up to 20 minutes before showtime (75% refund if >= 2 hours, 50% refund if < 2 hours). Concerts/Live events cannot be cancelled. Do not fetch booking history for general policy questions. Never invent artist biography or venue details.

3. get_user_booking_history
Use ONLY when the user asks about their own previous bookings, booking history, what they booked before, or their past concerts.
ALWAYS use this tool for such questions - never answer from conversation memory. This tool is the source of truth for the user's booking history. NEVER invent or infer previous bookings from conversation memory.

4. book_ticket_transaction
Use ONLY when the user explicitly confirms a booking after the assistant has shown the booking summary.
Examples: "Yes, proceed", "Confirm", "Book it", "Proceed with booking"
Before calling book_ticket_transaction, you MUST have: event_id, artist/event, date, venue, ticket category, quantity, price.
For events where get_available_seats returned has_seat_map=true, ask which specific seats the user wants and pass them as seat_numbers (e.g. ["N5", "N6"]) instead of a plain count - or if they say "any 2 seats"/don't care which, pass seats as a count instead and the system auto-picks available ones. For events with has_seat_map=false, always just pass seats as a count.
NEVER claim that a booking was successful unless book_ticket_transaction actually succeeds.
After book_ticket_transaction succeeds, provide the booking confirmation and clearly state the booking is reserved/pending until payment is completed via the payment_link - never say it is fully confirmed.
If book_ticket_transaction fails, clearly tell the user that the booking could not be completed.
NEVER create a booking merely because the user said "Book 2 VIP tickets..." - first show the booking summary and ask for confirmation.

5. Cancellations (check_cancellation_eligibility and cancel_booking)
If the user asks a booking-specific cancellation question (e.g., "Can I cancel my Pushpa 2 booking?", "How much will I get if I cancel?"), first use get_user_booking_history to find the exact booking_id. 
Then call check_cancellation_eligibility with the booking_id to find out the exact refund amount and cancellation fee. NEVER invent these rules or amounts yourself.
When the user asks to cancel, read out the expected refund amount and EXPLICITLY ask for confirmation (e.g., "Your refund will be Rs X. Would you like me to cancel it?").
Do NOT cancel immediately when the user only asks if cancellation is possible.
ONLY after they explicitly confirm ("Yes, cancel it"), use the cancel_booking tool.
Explain that a successful cancellation automatically implies the refund has been initiated or is pending.

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

QUERY INDEPENDENCE — CRITICAL:
Each new user message must be interpreted as-is, using ONLY the content of that message (plus any explicit reference back to a previous message).

NEVER automatically carry forward search intent, genre, mood, or keyword constraints from a previous message unless the NEW message itself references them.

Determining whether to carry context forward:
- Follow-up: user explicitly refers to the previous result or topic ("which of those is in Mumbai?", "that one", "the cheapest of these", "the Arijit Singh concert you mentioned").
  → Retain context. Call search_events using the same filters if helpful.
- New independent query: user states a fresh request ("events in Mumbai", "cheap tickets", "what is showing this weekend") with no reference to previous results.
  → Treat it as a new independent search. Call search_events with ONLY the parameters present in the NEW message. Do NOT add genre, mood, or keyword filters from earlier messages.

Examples:
  Turn 1 — User: "romantic concert" → call search_events(query="romantic concert")
  Turn 2 — User: "events in Mumbai" → call search_events(city="Mumbai") — do NOT pass query="romantic"

  Turn 1 — User: "show Arijit Singh concerts" → call search_events(query="Arijit Singh")
  Turn 2 — User: "which one is in Mumbai?" → this IS a follow-up → call search_events(query="Arijit Singh", city="Mumbai")

  Turn 1 — User: "Bollywood music" → call search_events(query="Bollywood music")
  Turn 2 — User: "cheap tickets" → this is a new independent query → call search_events() and present affordable options, do NOT restrict to Bollywood

When in doubt about whether a message is a follow-up, treat it as a new independent query.
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
        "search_events": _BASE_HANDLERS["search_events"],
        "get_ticket_categories": _BASE_HANDLERS["get_ticket_categories"],
        "get_available_seats": _BASE_HANDLERS["get_available_seats"],
        "book_ticket_transaction": lambda event_id, category, seats=None, seat_numbers=None: _BASE_HANDLERS["book_ticket_transaction"](
            user_id, event_id, category, seats=seats, seat_numbers=seat_numbers, source=source
        ),
        "get_user_booking_history": lambda temporal_intent=None, specific_month=None: _BASE_HANDLERS["get_user_booking_history"](user_id, temporal_intent, specific_month),
        "get_user_hosted_shows": lambda: _BASE_HANDLERS["get_user_hosted_shows"](user_id),
        "cancel_booking": lambda booking_id: _BASE_HANDLERS["cancel_booking"](user_id, booking_id),
        "check_cancellation_eligibility": lambda booking_id: _BASE_HANDLERS["check_cancellation_eligibility"](user_id, booking_id),
        "link_telegram_account": lambda email: _BASE_HANDLERS["link_telegram_account"](chat_id, email),
        "advise_seats": _BASE_HANDLERS["advise_seats"],
        "get_buy_advice": _BASE_HANDLERS["get_buy_advice"],
    }


class IntentClassification(pydantic.BaseModel):
    intent: str
    context_needed: bool

def classify_intent(message: str, history: list[types.Content]) -> IntentClassification:
    """
    Lightweight pre-flight semantic classifier.
    Determines intent and whether previous conversation context is needed.
    """
    prompt = """Classify the user's message into one of the following intents:
- OUT_OF_DOMAIN: Unrelated general knowledge, jokes, programming questions, weather, etc. Not related to events or bookings.
- EVENT_SEARCH: Searching for concerts, events, availability, tickets, prices.
- USER_DATA: Asking about their own bookings, wishlist, or hosted/submitted shows.
- FOLLOW_UP: A query that clearly references a previous result ("which one", "the cheapest of those").
- SEAT_ADVICE: User asks for seat or ticket‑category recommendations (e.g., "best seats", "cheap seats under 2000", "premium seats").
- GENERAL_LIVEWIRE: General questions about the platform capabilities.

Set context_needed to true ONLY if the user's query relies on previous conversation (e.g. "Which one is cheaper?", "book the second one").
If the user's query is a brand new independent search (e.g. "Find Bollywood concerts", "events in Mumbai"), set context_needed to false.
If there is no recent context provided, context_needed MUST be false.
"""
    # Just grab the last couple of turns for context
    recent_history = ""
    if history:
        for turn in history[-4:]:
            role = turn.role
            text = turn.parts[0].text if turn.parts else ""
            recent_history += f"{role}: {text}\n"
    else:
        recent_history = "None (this is the first message)"

    try:
        res = _client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=[
                types.Content(role="user", parts=[
                    types.Part.from_text(text=f"{prompt}\n\nRecent context:\n{recent_history}\n\nUser Message: {message}")
                ])
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=IntentClassification,
            )
        )
        data = json.loads(res.text)
        logger.info(f"Classifier result: {data}")
        return IntentClassification(**data)
    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        # Fail safe, not fail closed: we deliberately do NOT default to
        # EVENT_SEARCH here. Mislabeling a classifier failure as a
        # confident "EVENT_SEARCH" is exactly how an unknown/general
        # question used to silently sail through as if it had been
        # correctly classified. "UNKNOWN" is a distinct, non-committal
        # value: _run() treats it as "let the general agent (and the
        # DOMAIN SCOPE hard rule in SYSTEM_PROMPT) handle it" rather than
        # either blocking a possibly-legitimate booking query or quietly
        # relabeling it as something it was never actually classified as.
        return IntentClassification(intent="UNKNOWN", context_needed=True)


async def _run(effective_user_id: str, session_id: str, name: str, is_admin: bool, message: str, chat_id: str | None) -> str:
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    current_date_str = now.strftime("%Y-%m-%d %H:%M:%S")
    enriched_message = f"[Current Date (Asia/Kolkata): {current_date_str}] [User name: {name}] [User is_admin: {is_admin}] {message}"

    history = memory.load_history("customer", effective_user_id, session_id)
    
    # Pre-flight intent classification
    classification = classify_intent(message, history)


    # Demand query detection – treat as FOLLOW_UP with context_needed=True
    if _is_demand_query(message):
        logger.info("Demand query detected – forcing FOLLOW_UP with context_needed=True")
        classification = IntentClassification(intent="FOLLOW_UP", context_needed=True)

    # Seat/ticket recommendation query detection – treat as FOLLOW_UP with
    # context_needed=True so the full history (including the numbered
    # search results the event_id must be resolved from) stays available.
    if _is_seat_advice_query(message):
        logger.info("Seat advice query detected – forcing FOLLOW_UP with context_needed=True")
        classification = IntentClassification(intent="SEAT_ADVICE", context_needed=True)

    # Ordinal reference handling ("the first/second/third event", or an
    # explicit correction like "the third movie is Pushpa 2"). We
    # deliberately do NOT truncate history here: the numbered search
    # results (and any later correction of what an ordinal refers to) an
    # ordinal reference needs to resolve against can be further back than
    # the last few turns, and trimming risks cutting off the very listing
    # the model needs to re-search from. The full history plus the
    # ORDINAL EVENT REFERENCES rules in SYSTEM_PROMPT (re-run search_events
    # with the original filters, honor explicit corrections) are
    # responsible for correct resolution instead.
    if re.search(r"\b(first|second|third|fourth|fifth)\b", message, re.IGNORECASE):
        logger.info("Ordinal reference detected – keeping full history so the correct numbered search result can be re-resolved")

    # OUT_OF_DOMAIN gate — this is the actual enforcement point. Previously
    # classify_intent() correctly labeled unrelated general-knowledge
    # questions as OUT_OF_DOMAIN, but nothing ever read classification.intent
    # to act on it (it was only used for context_needed and the two regex
    # overrides above), so every message - regardless of classified intent -
    # fell through to gemini_loop.run_agent() and got a general-purpose
    # Gemini answer. This short-circuits before that call, with a static
    # deterministic reply (no extra Gemini call, ₹0 incremental AI cost).
    # The demand/seat-advice regex overrides above run first and can
    # already flip classification away from OUT_OF_DOMAIN for obviously
    # in-domain phrasing, so this only fires for what the classifier still
    # considers out-of-domain after those checks.
    if classification.intent == "OUT_OF_DOMAIN":
        logger.info("OUT_OF_DOMAIN intent detected – short-circuiting before gemini_loop.run_agent()")
        greeting = f"Hey {name}, " if name else ""
        reply = (
            f"{greeting}that's outside what I can help with here — I'm LiveWire's booking assistant. "
            "I can help you find concerts, movies, or other events, check ticket prices and availability, "
            "or manage your bookings. Is there something like that I can help with?"
        )
        memory.save_turn("customer", effective_user_id, session_id, message, reply)
        return reply

    if not classification.context_needed:
        if history:
            logger.info("Context not needed but prior history exists – retaining it for potential follow‑up.")
        else:
            logger.info("Context not needed. Dropping history for this request.")
            history = []

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