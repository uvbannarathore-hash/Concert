"""
admin_tools.py — Tools for the admin AI assistant, ported 1:1 from the n8n
"Admin Assistant" workflow's 13 tool nodes (list_events, update_event,
cancel_event, delete_event, update_pricing, check_seat_availability,
create_event1, get_user_bookings, get_all_users_booking_report,
get_revenue_report, get_event_revenue, get_refund_list, update_seats).

Each tool is a plain Python function operating on supabase_admin directly
(no more going out over HTTP to n8n's cloud instance and back). Descriptions
below are carried over from the n8n tool nodes' toolDescription fields
almost verbatim, since those were already tuned through real usage.
"""

from app.supabase_client import supabase_admin


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def list_events() -> dict:
    result = supabase_admin.table("events").select("*").execute()
    return {"events": result.data}


def update_event(
    event_id: str,
    artist_name: str = None,
    venue_name: str = None,
    city: str = None,
    event_date: str = None,
    event_time: str = None,
    event_type: str = None,
    artist_id: str = None,
    venue_id: str = None,
    image_url: str = None,
    latitude: str = None,
    longitude: str = None,
) -> dict:
    fields = {
        "artist_name": artist_name,
        "venue_name": venue_name,
        "city": city,
        "event_date": event_date,
        "event_time": event_time,
        "event_type": event_type,
        "artist_id": artist_id,
        "venue_id": venue_id,
        "image_url": image_url,
        "latitude": latitude,
        "longitude": longitude,
    }
    # Only send fields the admin actually mentioned - leave the rest
    # untouched, matching the n8n tool's "leave unchanged if not mentioned"
    # instruction.
    fields = {k: v for k, v in fields.items() if v is not None}
    if not fields:
        return {"error": "No fields provided to update."}

    result = supabase_admin.table("events").update(fields).eq("event_id", event_id).execute()
    if not result.data:
        return {"error": f"No event found with event_id {event_id}"}
    return {"status": "updated", "event_id": event_id, "updated_fields": list(fields.keys())}


def cancel_event(event_id: str, new_status: str) -> dict:
    result = (
        supabase_admin.table("events")
        .update({"status": new_status})
        .eq("event_id", event_id)
        .execute()
    )
    if not result.data:
        return {"error": f"No event found with event_id {event_id}"}
    return {"status": "updated", "event_id": event_id, "new_status": new_status}


def delete_event(event_id: str) -> dict:
    result = supabase_admin.table("events").delete().eq("event_id", event_id).execute()
    if not result.data:
        return {"error": f"No event found with event_id {event_id}"}
    return {"status": "deleted", "event_id": event_id}


def update_pricing(event_id: str, category: str, price_inr: float) -> dict:
    result = (
        supabase_admin.table("ticket_categories")
        .update({"price_inr": price_inr})
        .eq("event_id", event_id)
        .eq("category", category)
        .execute()
    )
    if not result.data:
        return {"error": f"No ticket category '{category}' found for event {event_id}"}
    return {"status": "updated", "event_id": event_id, "category": category, "new_price_inr": price_inr}


def check_seat_availability(event_id: str) -> dict:
    result = (
        supabase_admin.table("ticket_categories")
        .select("category, price_inr, total_seats, available_seats")
        .eq("event_id", event_id)
        .execute()
    )
    if not result.data:
        return {"error": f"No ticket categories found for event {event_id}"}
    categories = [
        {**row, "sold_seats": row["total_seats"] - row["available_seats"]}
        for row in result.data
    ]
    return {"event_id": event_id, "categories": categories}


def create_event1(
    event_id: str,
    artist_id: str,
    artist_name: str,
    venue_id: str,
    venue_name: str,
    city: str,
    event_date: str,
    event_time: str,
    event_type: str,
    categories: list,
    image_url: str = None,
    latitude: float = None,
    longitude: float = None,
) -> dict:
    """
    Creates a new event with any number of ticket categories, via the
    create_event_with_pricing RPC (already migrated off the old hardcoded
    VIP/Gold/Silver/General signature to accept a dynamic jsonb array).

    categories: list of {"category": str, "price": number, "seats": number}
    """
    if not categories:
        return {"error": "At least one ticket category is required."}

    result = supabase_admin.rpc(
        "create_event_with_pricing",
        {
            "p_event_id": event_id,
            "p_artist_id": artist_id,
            "p_artist_name": artist_name,
            "p_venue_id": venue_id,
            "p_venue_name": venue_name,
            "p_city": city,
            "p_event_date": event_date,
            "p_event_time": event_time,
            "p_event_type": event_type,
            "p_categories": categories,
            "p_image_url": image_url,
            "p_latitude": latitude,
            "p_longitude": longitude,
        },
    ).execute()
    return result.data


def get_user_bookings(identifier: str) -> dict:
    """identifier: the user's email or user_id."""
    result = supabase_admin.rpc("get_user_bookings", {"p_identifier": identifier}).execute()
    return {"bookings": result.data}


def get_all_users_booking_report() -> dict:
    result = supabase_admin.rpc("get_all_users_booking_report", {}).execute()
    return {"report": result.data}


def get_revenue_report() -> dict:
    result = supabase_admin.rpc("get_revenue_report", {}).execute()
    return {"report": result.data}


def get_event_revenue(event_id: str) -> dict:
    result = supabase_admin.rpc("get_event_revenue", {"p_event_id": event_id}).execute()
    return {"event_id": event_id, "revenue": result.data}


def get_refund_list(event_id: str) -> dict:
    result = supabase_admin.rpc("get_refund_list", {"p_event_id": event_id}).execute()
    return {"event_id": event_id, "refund_list": result.data}


def update_seats(event_id: str, category: str, new_total_seats: int) -> dict:
    result = supabase_admin.rpc(
        "update_ticket_seats",
        {"p_event_id": event_id, "p_category": category, "p_new_total_seats": new_total_seats},
    ).execute()
    return result.data


# ---------------------------------------------------------------------------
# Gemini function declarations (JSON schema) + handler map
# ---------------------------------------------------------------------------

FUNCTION_DECLARATIONS = [
    {
        "name": "list_events",
        "description": "Use this to look up existing events - to find an event_id before "
        "updating, cancelling, or deleting, or when the admin asks what's currently listed.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "update_event",
        "description": "Use this to modify details of an existing event. Always confirm the "
        "event_id via list_events first if not already known. Only pass fields the admin "
        "actually mentioned - leave everything else unset.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The ID of the event to update, found via list_events if not already known."},
                "artist_name": {"type": "string", "description": "The artist, performer, or title name."},
                "venue_name": {"type": "string", "description": "The venue name."},
                "city": {"type": "string", "description": "The city where the event is held."},
                "event_date": {"type": "string", "description": "Event date in YYYY-MM-DD format."},
                "event_time": {"type": "string", "description": "Event time e.g. 19:00."},
                "event_type": {"type": "string", "description": "One of: Concert, Movie, Comedy Show, Music Show, Play, Sports."},
                "artist_id": {"type": "string", "description": "ID for the artist or performer."},
                "venue_id": {"type": "string", "description": "ID for the venue."},
                "image_url": {"type": "string", "description": "New image URL, from an [Uploaded image URL: ...] segment if present."},
                "latitude": {"type": "string", "description": "New venue latitude, from a [Venue Location: lat,lng] segment if present."},
                "longitude": {"type": "string", "description": "New venue longitude, from a [Venue Location: lat,lng] segment if present."},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "cancel_event",
        "description": "Use this to change an event's status between 'Upcoming' and 'Cancelled'. "
        "Use 'Cancelled' when the admin wants to cancel an event, and 'Upcoming' when the admin "
        "wants to reactivate a previously cancelled event. Always confirm with the admin before "
        "changing status, especially for cancellation.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The ID of the event to cancel."},
                "new_status": {"type": "string", "description": "The new status to set: 'Upcoming' or 'Cancelled'."},
            },
            "required": ["event_id", "new_status"],
        },
    },
    {
        "name": "delete_event",
        "description": "Use this ONLY after the admin has explicitly confirmed deletion "
        "(e.g. said 'yes, delete it'). This is permanent and cannot be undone. NEVER call this "
        "tool on the first request - always get explicit confirmation first.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The ID of the event to permanently delete."},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "update_pricing",
        "description": "Use this to change the ticket price for a specific category (any "
        "category name that exists for that event) of an existing event. Confirm the new price "
        "with the admin before calling this. Never reuse an old price from memory - always use "
        "the latest price explicitly provided by the admin.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID to update."},
                "category": {"type": "string", "description": "The ticket category to update, e.g. Gold, Silver, VIP, General."},
                "price_inr": {"type": "number", "description": "The new ticket price in INR (numeric, not text)."},
            },
            "required": ["event_id", "category", "price_inr"],
        },
    },
    {
        "name": "check_seat_availability",
        "description": "Use this tool to check ticket seat availability for a specific event - "
        "total seats, available seats, and price for each category. Sold seats are calculated "
        "as (total_seats - available_seats) for each category.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID to check seat info for."},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "create_event1",
        "description": "Creates a new event. When the admin asks to create an event, ALWAYS "
        "ask what ticket categories they want (there is no fixed set - any names, any number "
        "from 1 upwards, e.g. VIP, Gold, Early Bird, Balcony, Student). For EACH category, "
        "collect its price (INR) and total seat count before calling this. Do not invent "
        "category names, prices, or seat counts on your own.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "A short unique ID for the event, e.g. EVTARIJIT1512."},
                "artist_id": {"type": "string", "description": "A short ID for the artist/performer."},
                "artist_name": {"type": "string", "description": "The artist, performer, or movie/show title."},
                "venue_id": {"type": "string", "description": "A short ID for the venue."},
                "venue_name": {"type": "string", "description": "The venue name."},
                "city": {"type": "string", "description": "The city where the event is held."},
                "event_date": {"type": "string", "description": "Event date in YYYY-MM-DD format."},
                "event_time": {"type": "string", "description": "Event time in 24-hour HH:MM format, e.g. 19:00."},
                "event_type": {"type": "string", "description": "One of: Concert, Movie, Comedy Show, Music Show, Play, Sports."},
                "categories": {
                    "type": "array",
                    "description": "Array of ticket categories for this event. Each item has category (string), price (number, INR), and seats (number, total seats for that category).",
                    "items": {
                        "type": "object",
                        "properties": {
                            "category": {"type": "string"},
                            "price": {"type": "number"},
                            "seats": {"type": "integer"},
                        },
                        "required": ["category", "price", "seats"],
                    },
                },
                "image_url": {"type": "string", "description": "Poster image URL, from an [Uploaded image URL: ...] segment if present."},
                "latitude": {"type": "number", "description": "Venue latitude, from a [Venue Location: lat,lng] segment if present."},
                "longitude": {"type": "number", "description": "Venue longitude, from a [Venue Location: lat,lng] segment if present."},
            },
            "required": ["event_id", "artist_id", "artist_name", "venue_id", "venue_name", "city", "event_date", "event_time", "event_type", "categories"],
        },
    },
    {
        "name": "get_user_bookings",
        "description": "Use this to get all bookings made by a specific user, identified by "
        "email or user_id.",
        "parameters": {
            "type": "object",
            "properties": {
                "identifier": {"type": "string", "description": "The user email or user_id to look up bookings for."},
            },
            "required": ["identifier"],
        },
    },
    {
        "name": "get_all_users_booking_report",
        "description": "Use this to get a summary report of all users and how many "
        "bookings/seats each has made.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_revenue_report",
        "description": "Use this to get a summary of total revenue across all events/bookings.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_event_revenue",
        "description": "Use this to get the total revenue generated by one specific event.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID to get revenue for."},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "get_refund_list",
        "description": "Use this to get all bookings made by a specific user, identified by "
        "email or user_id. Also use this to see who needs a refund after cancelling an event.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID that was cancelled, to see who needs a refund."},
            },
            "required": ["event_id"],
        },
    },
    {
        "name": "update_seats",
        "description": "Use this to change the total seat count (capacity) for a specific "
        "ticket category of an event. This is different from update_pricing - use this ONLY "
        "when the admin wants to change how many seats/tickets are available for a category, "
        "not the price.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID."},
                "category": {"type": "string", "description": "Ticket category, e.g. VIP, Gold, Silver, General."},
                "new_total_seats": {"type": "integer", "description": "The new total seat count for this category."},
            },
            "required": ["event_id", "category", "new_total_seats"],
        },
    },
]

TOOL_HANDLERS = {
    "list_events": list_events,
    "update_event": update_event,
    "cancel_event": cancel_event,
    "delete_event": delete_event,
    "update_pricing": update_pricing,
    "check_seat_availability": check_seat_availability,
    "create_event1": create_event1,
    "get_user_bookings": get_user_bookings,
    "get_all_users_booking_report": get_all_users_booking_report,
    "get_revenue_report": get_revenue_report,
    "get_event_revenue": get_event_revenue,
    "get_refund_list": get_refund_list,
    "update_seats": update_seats,
}