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

def advise_seats(event_id: str, max_price: float = None, category: str = None, quantity: int = 1, preference: str = None, max_results: int = 5) -> dict:
    """Provide deterministic seat or ticket-category recommendations.
    Parameters:
        event_id: ID of the event (required).
        max_price: Optional upper price filter (inclusive).
        category: Optional filter to a specific ticket category.
        quantity: Number of seats the user wants together (default 1).
        preference: Hint influencing sorting:
            - "premium" → higher price first.
            - "cheap", "default", "best_value" → lower price first.
        max_results: Maximum number of recommendations to return.
    Returns a dict with a "recommendations" list of human‑readable strings.
    Sorting follows the spec: price ASC (or DESC for premium), then availability DESC,
    then category name ASC, row ASC, seat number ASC. For events without a seat map,
    returns category‑level "Any" recommendations.
    """
    # Fetch categories with pricing. voice_db.get_ticket_categories() does NOT
    # return a {category_name: meta} mapping - it returns a flat result dict:
    #   {"success": True, "message": "...", "categories": [
    #       {"category": "VIP", "price_inr": 5000, "available_seats": 10}, ...
    #   ]}
    # or {"success": False, "message": "..."} when there are none. Iterating
    # .items() on that outer dict directly (as this function used to) walks
    # over ("success", True) / ("message", str) / ("categories", list) pairs
    # instead of real categories, which is why `meta` was a bool at runtime.
    cat_result = voice_db.get_ticket_categories(event_id)
    if not isinstance(cat_result, dict) or not cat_result.get('success'):
        message = cat_result.get('message') if isinstance(cat_result, dict) else None
        return {"recommendations": [], "message": message or "Could not retrieve ticket categories for this event."}

    raw_categories = cat_result.get('categories')
    if not isinstance(raw_categories, list):
        return {"recommendations": [], "message": "Ticket category data for this event is unavailable right now."}

    # Normalize into {category_name: {"price": ..., "available_seats": ...}},
    # skipping any malformed entries rather than crashing on them (per-row
    # defensive handling - never fabricate a price or category we didn't
    # actually get back from the DB).
    categories: dict[str, dict] = {}
    for entry in raw_categories:
        if not isinstance(entry, dict):
            continue
        name = entry.get('category')
        price = entry.get('price_inr')
        if name is None or price is None:
            continue
        categories[name] = {
            'price': price,
            'available_seats': entry.get('available_seats'),
        }

    # Apply category filter if provided
    if category:
        categories = {k: v for k, v in categories.items() if k == category}
    # Filter by max_price if provided
    if max_price is not None:
        categories = {k: v for k, v in categories.items() if v.get('price') is not None and v['price'] <= max_price}

    recommendations = []
    # Gather seats per category
    for cat, meta in categories.items():
        seats_info = voice_db.get_available_seats(event_id, cat)
        if not isinstance(seats_info, dict):
            continue

        if seats_info.get('has_seat_map'):
            available = seats_info.get('available_seats')
            if not isinstance(available, list):
                available = []
            # Build per-seat entries from ACTUAL available seats only - the
            # row key returned here is "seat_row", not "row".
            for seat in available:
                if not isinstance(seat, dict):
                    continue
                row = seat.get('seat_row')
                number = seat.get('seat_number')
                if number is None:
                    continue
                recommendations.append({
                    'price': meta.get('price'),
                    'availability': len(available),
                    'category': cat,
                    'row': row,
                    'seat_number': number,
                    'seat_repr': f"{row}{number}" if row is not None else str(number)
                })
        else:
            # Non-seat-map category: a single category-level "Any" recommendation,
            # using the availability count already returned by get_ticket_categories
            # (available_seats on the ticket_categories row) - never inventing seats.
            recommendations.append({
                'price': meta.get('price'),
                'availability': meta.get('available_seats') or 0,
                'category': cat,
                'row': None,
                'seat_number': None,
                'seat_repr': "Any"
            })
    # Sort according to spec, handling preference
    def _sort_key(item):
        price = item['price'] if item['price'] is not None else float('inf')
        if preference and preference.lower() == "premium":
            # higher price is better for premium preference
            price = -price if price != float('inf') else float('-inf')
        return (
            price,
            -item['availability'],
            item['category'],
            item['row'] or "",
            item['seat_number'] if item['seat_number'] is not None else -1,
        )
    recommendations.sort(key=_sort_key)
    # Consolidate consecutive seats when quantity > 1
    final = []
    i = 0
    while i < len(recommendations) and len(final) < max_results:
        rec = recommendations[i]
        if quantity > 1:
            # Look ahead for consecutive seats in same category and row
            row = rec['row']
            start_num = rec['seat_number']
            cat = rec['category']
            consecutive = [rec]
            for j in range(i + 1, len(recommendations)):
                nxt = recommendations[j]
                if (
                    nxt['category'] == cat
                    and nxt['row'] == row
                    and nxt['seat_number'] == start_num + len(consecutive)
                ):
                    consecutive.append(nxt)
                if len(consecutive) == quantity:
                    break
            if len(consecutive) == quantity:
                seat_range = f"{row}{start_num}-{row}{start_num + quantity - 1}" if row else f"{start_num}-{start_num + quantity - 1}"
                final.append(f"Category: {rec['category']}, Seats: {seat_range}, Price per seat: INR {rec['price']}")
                i += quantity
                continue
        # Fallback single seat recommendation
        final.append(f"Category: {rec['category']}, Seat: {rec['seat_repr']}, Price: INR {rec['price']}")
        i += 1
    return {"recommendations": final[:max_results]}



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

def check_cancellation_eligibility(user_id: str, booking_id: str) -> dict:
    from app.services.cancellation_service import get_cancellation_eligibility as service_check
    return service_check(booking_id, user_id)


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
# Seat Upgrade Monitor Tools
# ---------------------------------------------------------------------------

def request_seat_upgrade(user_id: str, booking_id: str, desired_category: str) -> dict:
    # 1. Fetch booking
    booking_res = supabase_admin.table("bookings").select("*").eq("booking_id", booking_id).eq("user_id", user_id).execute()
    if not booking_res.data:
        return {"success": False, "message": "Booking not found or does not belong to you."}
    booking = booking_res.data[0]
    
    if booking["status"] != "Confirmed":
        return {"success": False, "message": f"Cannot upgrade booking with status: {booking['status']}. Only Confirmed bookings can be upgraded."}
        
    current_category = booking["category"]
    if current_category == desired_category:
        return {"success": False, "message": "You are already booked in this category."}
        
    # Check if category exists
    cat_res = supabase_admin.table("ticket_categories").select("*").eq("event_id", booking["event_id"]).eq("category", desired_category).execute()
    if not cat_res.data:
        return {"success": False, "message": f"Category {desired_category} does not exist for this event."}
        
    # Upsert logic to handle duplicates, but since we have a unique index on active/notified
    # we can just try inserting
    try:
        supabase_admin.table("seat_upgrade_requests").insert({
            "user_id": user_id,
            "original_booking_id": booking_id,
            "event_id": booking["event_id"],
            "current_category": current_category,
            "desired_category": desired_category,
            "status": "active"
        }).execute()
        return {"success": True, "message": f"Upgrade requested to {desired_category}. We will notify you if seats become available."}
    except Exception as e:
        if "idx_seat_upgrade_requests_unique_active" in str(e):
            # The AI might have called request_seat_upgrade instead of approve_seat_upgrade
            # because the user just said "Upgrade my booking". Check if it's actually notified.
            req_res = supabase_admin.table("seat_upgrade_requests").select("status").eq("original_booking_id", booking_id).eq("user_id", user_id).eq("desired_category", desired_category).in_("status", ["notified", "payment_pending", "refund_pending"]).execute()
            if req_res.data:
                # Intercept and automatically route to the approval flow
                return approve_seat_upgrade(user_id, booking_id)
                
            return {"success": False, "message": f"You already have an active monitoring request for {desired_category}."}
        return {"success": False, "message": f"Could not request upgrade: {e}"}

def direct_seat_downgrade(user_id: str, booking_id: str, desired_category: str) -> dict:
    # 1. Fetch booking
    booking_res = supabase_admin.table("bookings").select("*").eq("booking_id", booking_id).eq("user_id", user_id).execute()
    if not booking_res.data:
        return {"success": False, "message": "Booking not found or does not belong to you."}
    booking = booking_res.data[0]
    
    if booking["status"] != "Confirmed":
        return {"success": False, "message": f"Cannot modify booking with status: {booking['status']}. Only Confirmed bookings can be modified."}
        
    current_category = booking["category"]
    if current_category == desired_category:
        return {"success": False, "message": "You are already booked in this category."}
        
    # Check if category exists
    cat_res = supabase_admin.table("ticket_categories").select("*").eq("event_id", booking["event_id"]).in_("category", [current_category, desired_category]).execute()
    cats = {c["category"]: c for c in cat_res.data}
    
    if desired_category not in cats or current_category not in cats:
        return {"success": False, "message": "Categories not found for this event."}
        
    desired_cat_data = cats[desired_category]
    current_cat_data = cats[current_category]
    
    # Verify it is economically a downgrade
    if float(desired_cat_data["price_inr"]) >= float(current_cat_data["price_inr"]):
        return {"success": False, "message": f"The requested category {desired_category} is not cheaper than your current category {current_category}. This tool is for downgrades only."}

    # Cancel any existing active requests for this booking to prevent unique constraint errors
    supabase_admin.table("seat_upgrade_requests").update({"status": "cancelled"}).eq("original_booking_id", booking_id).in_("status", ["active"]).execute()

    # Insert downgrade request directly as 'notified' to bypass cron/email triggers
    try:
        supabase_admin.table("seat_upgrade_requests").insert({
            "user_id": user_id,
            "original_booking_id": booking_id,
            "event_id": booking["event_id"],
            "current_category": current_category,
            "desired_category": desired_category,
            "status": "notified"
        }).execute()
        
        # Reuse existing approve_seat_upgrade flow for downgrade DB/refund sync
        return approve_seat_upgrade(user_id, booking_id)
        
    except Exception as e:
        return {"success": False, "message": f"Could not process downgrade: {e}"}

def approve_seat_upgrade(user_id: str, booking_id: str) -> dict:
    from app.services.cancellation_service import _fetch_payment_and_refunds, _reconcile_refund_state
    from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
    import razorpay
    
    # 1. Find the request in any pending state
    req_res = supabase_admin.table("seat_upgrade_requests").select("*").eq("original_booking_id", booking_id).eq("user_id", user_id).in_("status", ["notified", "processing", "payment_pending", "refund_pending"]).execute()
    
    if not req_res.data:
        return {"success": False, "message": "No active upgrade request found for this booking."}
    
    request = req_res.data[0]
    req_id = request["id"]
    
    if request["status"] == "payment_pending":
        return {"success": False, "message": "You already approved this upgrade. Please complete the pending payment."}
        
    # Attempt to lock and claim if it's notified or stuck in processing
    if request["status"] in ["notified", "processing"]:
        claim_res = supabase_admin.rpc("claim_seat_upgrade", {"p_request_id": req_id, "p_user_id": user_id}).execute()
        if not claim_res.data:
            return {"success": False, "message": "This upgrade request is currently being processed by another action or is no longer valid."}
        # Reload request state after claiming
        request["status"] = "processing"
        
    desired_category = request["desired_category"]
    current_category = request["current_category"]
    
    cat_res = supabase_admin.table("ticket_categories").select("*").eq("event_id", request["event_id"]).in_("category", [current_category, desired_category]).execute()
    cats = {c["category"]: c for c in cat_res.data}
    
    if desired_category not in cats or current_category not in cats:
        return {"success": False, "message": "Categories not found."}
        
    booking_res = supabase_admin.table("bookings").select("*").eq("booking_id", booking_id).execute()
    booking = booking_res.data[0]
    
    seats_booked = booking["seats_booked"]
    
    desired_cat_data = cats[desired_category]
    current_cat_data = cats[current_category]
    
    new_price = float(desired_cat_data["price_inr"]) * seats_booked
    old_price = float(booking.get("total_amount") or (float(current_cat_data["price_inr"]) * seats_booked))
    price_diff = new_price - old_price
    
    if price_diff > 0:
        # More expensive. Generate payment link.
        # We need to ensure we don't double generate.
        # Check if availability is still there before generating payment link
        if desired_cat_data["available_seats"] < seats_booked:
            supabase_admin.table("seat_upgrade_requests").update({"status": "active"}).eq("id", req_id).execute()
            return {"success": False, "message": f"Sorry, {desired_category} is no longer available. You have been returned to the active monitoring queue."}
            
        razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        amount_paise = int(round(price_diff * 100))
        link_payload = {
            "amount": amount_paise,
            "currency": "INR",
            "description": f"Upgrade to {desired_category} for {seats_booked} seats",
            "notify": {"sms": False, "email": False},
            "notes": {"upgrade_request_id": req_id, "booking_id": booking_id},
        }
        try:
            payment_link = razorpay_client.payment_link.create(link_payload)
            supabase_admin.table("seat_upgrade_requests").update({
                "status": "payment_pending",
            }).eq("id", req_id).execute()
            
            return {
                "success": True, 
                "message": f"The new seats cost more. Please pay the difference of INR {price_diff} using this secure link: {payment_link.get('short_url')} . The upgrade will be processed automatically once payment is confirmed."
            }
        except Exception as e:
            supabase_admin.table("seat_upgrade_requests").update({"status": "notified"}).eq("id", req_id).execute()
            return {"success": False, "message": f"Could not generate payment link: {e}"}
            
    elif price_diff < 0:
        # Cheaper. Refund difference.
        
        # If it's already refund_pending, we skip the DB swap because we already swapped categories in the DB previously.
        if request["status"] != "refund_pending":
            # DB First: Safely swap seats and update booking inside DB transaction
            try:
                # RPC will throw if unavailable
                downgrade_res = supabase_admin.rpc("process_seat_downgrade", {"p_request_id": req_id}).execute()
            except Exception as e:
                # If unavailable, return to active monitor
                if "Not enough seats" in str(e):
                    supabase_admin.table("seat_upgrade_requests").update({"status": "active"}).eq("id", req_id).execute()
                    return {"success": False, "message": f"Sorry, {desired_category} is no longer available. You have been returned to the active monitoring queue."}
                return {"success": False, "message": f"Could not downgrade booking: {e}"}
        
        razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))
        refund_amount = abs(price_diff)
        refund_amount_paise = int(round(refund_amount * 100))
        
        razorpay_payment_id = booking.get("razorpay_payment_id")
        if not razorpay_payment_id:
            # We are stuck in refund_pending but cannot refund. 
            return {"success": False, "message": "Booking was downgraded successfully, but cannot process refund because original payment ID is missing."}
            
        try:
            payment_info, refunds_list = _fetch_payment_and_refunds(razorpay_payment_id)
            captured_amount = payment_info.get("amount") or 0
            recon = _reconcile_refund_state(payment_info, refunds_list, captured_amount)
            
            # Check if there's enough refundable amount
            if recon["remaining_refundable_amount"] < refund_amount_paise:
                # If we already have a matching refund (from a previous retry of this same downgrade), use it!
                matching = recon.get("matching_refund")
                if matching and (matching.get("amount") or 0) >= refund_amount_paise:
                    refund_id = matching.get("id")
                    if not refund_id:
                        raise Exception("Found matching refund but it had no ID.")
                    
                    supabase_admin.table("seat_upgrade_requests").update({
                        "status": "upgraded",
                        "refund_id": refund_id
                    }).eq("id", req_id).execute()
                    return {"success": True, "message": f"Successfully downgraded to {desired_category}. A refund of INR {refund_amount} has been initiated."}
                
                return {"success": False, "message": "Booking was downgraded successfully, but cannot refund difference: Payment is already partially or fully refunded."}
                
            refund = razorpay_client.payment.refund(razorpay_payment_id, {
                "amount": refund_amount_paise,
                "notes": {"booking_id": booking_id, "reason": "seat_upgrade_downgrade", "upgrade_request_id": req_id}
            })
            
            refund_id = refund.get("id") if isinstance(refund, dict) else None
            if not refund_id:
                # Treat missing refund ID as a failure so we don't falsely claim success without an audit trail
                raise Exception("Razorpay refund API succeeded but did not return a valid refund ID.")
            
            # 3. Update request
            supabase_admin.table("seat_upgrade_requests").update({
                "status": "upgraded",
                "refund_id": refund_id
            }).eq("id", req_id).execute()
            
            return {"success": True, "message": f"Successfully downgraded to {desired_category}. A refund of INR {refund_amount} has been initiated."}
            
        except Exception as e:
            # Remain in refund_pending for future retry
            return {"success": False, "message": f"Booking downgraded to {desired_category} successfully, but Razorpay refund failed: {e}. You can ask me to approve the upgrade again later to retry the refund."}
    
    else:
        # Equal price
        if request["status"] != "processing":
            return {"success": False, "message": "Request state invalid for equal price swap."}
            
        try:
            # Since there is no refund or payment, we can just use the finalize flow, but we can also use process_seat_downgrade and then immediately set to upgraded.
            downgrade_res = supabase_admin.rpc("process_seat_downgrade", {"p_request_id": req_id}).execute()
            
            supabase_admin.table("seat_upgrade_requests").update({
                "status": "upgraded"
            }).eq("id", req_id).execute()
            
            return {"success": True, "message": f"Successfully upgraded to {desired_category} at no extra cost!"}
        except Exception as e:
            if "Not enough seats" in str(e):
                supabase_admin.table("seat_upgrade_requests").update({"status": "active"}).eq("id", req_id).execute()
                return {"success": False, "message": f"Sorry, {desired_category} is no longer available. You have been returned to the monitoring queue."}
            return {"success": False, "message": f"Upgrade failed: {e}"}

# ---------------------------------------------------------------------------
# Concierge Agent Tools (Mocked external APIs)
# ---------------------------------------------------------------------------

def _get_venue_coordinates(event_id: str) -> tuple[float, float] | None:
    """Helper to fetch venue coordinates for a given event_id."""
    result = supabase_admin.table("events").select("venue_id, latitude, longitude").eq("event_id", event_id).execute()
    if result.data:
        row = result.data[0]
        # check event row first
        if row.get("latitude") is not None and row.get("longitude") is not None:
            return float(row["latitude"]), float(row["longitude"])
        # fallback to venues table if event doesn't have it explicitly duplicated
        if row.get("venue_id"):
            v_result = supabase_admin.table("venues").select("latitude, longitude").eq("venue_id", row["venue_id"]).execute()
            if v_result.data and v_result.data[0].get("latitude") is not None:
                return float(v_result.data[0]["latitude"]), float(v_result.data[0]["longitude"])
    return None

import logging
import httpx
import math
from functools import lru_cache

logger = logging.getLogger("customer_tools")

@lru_cache(maxsize=128)
def maps_directions(event_id: str, destination_lat: float, destination_lon: float) -> dict:
    """Real OSM OSRM directions API."""
    coords = _get_venue_coordinates(event_id)
    if not coords:
        return {"success": False, "message": "Could not determine origin venue coordinates."}
    
    origin_lat, origin_lon = coords
    
    # Try public OSRM for driving route
    try:
        url = f"https://router.project-osrm.org/route/v1/driving/{origin_lon},{origin_lat};{destination_lon},{destination_lat}?overview=false"
        resp = httpx.get(url, timeout=5.0, headers={"User-Agent": "ConcertApp/1.0"})
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") == "Ok" and data.get("routes"):
            route = data["routes"][0]
            dist_km = route["distance"] / 1000.0
            time_mins = route["duration"] / 60.0
            cab_fare = dist_km * 20 + 50
            return {
                "success": True,
                "distance_km": round(dist_km, 2),
                "estimated_time_mins": round(time_mins),
                "estimated_cab_fare_inr": round(cab_fare),
                "mode": "driving",
                "is_fallback": False
            }
    except Exception as e:
        logger.error(f"OSRM failed: {e}")
    
    # Haversine deterministic fallback
    lat1, lon1 = math.radians(origin_lat), math.radians(origin_lon)
    lat2, lon2 = math.radians(destination_lat), math.radians(destination_lon)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    dist_km = 6371 * c
    
    # Driving is usually ~1.3x straight line distance
    driving_dist_km = dist_km * 1.3
    time_mins = driving_dist_km * 3 # roughly 20km/h
    cab_fare = driving_dist_km * 20 + 50
    return {
        "success": True,
        "distance_km": round(driving_dist_km, 2),
        "estimated_time_mins": round(time_mins),
        "estimated_cab_fare_inr": round(cab_fare),
        "mode": "driving",
        "is_fallback": True,
        "message": "Used estimated straight-line routing due to OSM routing unavailability."
    }

@lru_cache(maxsize=128)
def restaurant_suggestions(event_id: str, budget_inr: float = 1500) -> dict:
    """Real OSM Overpass API restaurant search near the venue."""
    coords = _get_venue_coordinates(event_id)
    if not coords:
        return {"success": False, "message": "Could not determine event venue coordinates to find nearby restaurants."}
    
    lat, lon = coords
    
    # Bounding box roughly 2km
    lat_delta = 0.02
    lon_delta = 0.02
    
    restaurants = []
    
    try:
        # Fetch from local Supabase cache instead of live Overpass API
        result = supabase_admin.table("restaurants").select("*") \
            .gte("latitude", lat - lat_delta).lte("latitude", lat + lat_delta) \
            .gte("longitude", lon - lon_delta).lte("longitude", lon + lon_delta) \
            .execute()
            
        if result.data:
            for row in result.data:
                r_lat = row["latitude"]
                r_lon = row["longitude"]
                
                # Calculate exact Haversine distance
                lat1, lon1 = math.radians(lat), math.radians(lon)
                lat2, lon2 = math.radians(r_lat), math.radians(r_lon)
                dlon = lon2 - lon1
                dlat = lat2 - lat1
                a = math.sin(dlat / 2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2)**2
                c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                dist_km = 6371 * c
                
                # Filter by 2000m radius and budget
                if dist_km <= 2.0:
                    base_cost = row.get("estimated_cost_for_two_inr") or 1500
                    if base_cost <= budget_inr * 1.5:
                        restaurants.append({
                            "name": row["name"],
                            "cuisine": row.get("cuisine", "Mixed"),
                            "lat": r_lat,
                            "lon": r_lon,
                            "estimated_cost_for_two_inr": base_cost,
                            "is_cost_estimated": True
                        })
            
            if restaurants:
                logger.info("Plan My Night restaurants: Returning CACHED OSM data")
                return {"success": True, "restaurants": restaurants[:5], "is_fallback": False}
    except Exception as e:
        logger.warning(f"Failed to query cached restaurants ({e}). Falling back instantly.")
            
    # Fallback to static mock data near the venue coordinates
    logger.info("Plan My Night restaurants: Returning FALLBACK data")
    return {
        "success": True,
        "is_fallback": True,
        "message": "Live OSM restaurant search unavailable; returning fallback suggestions.",
        "restaurants": [
            {"name": "The Grand Local (Fallback)", "cuisine": "North Indian", "lat": lat + 0.001, "lon": lon + 0.001, "estimated_cost_for_two_inr": 1200, "is_cost_estimated": True},
            {"name": "Spice Route (Fallback)", "cuisine": "Pan Asian", "lat": lat - 0.002, "lon": lon + 0.002, "estimated_cost_for_two_inr": 1800, "is_cost_estimated": True},
            {"name": "Bistro Cafe (Fallback)", "cuisine": "Continental", "lat": lat + 0.003, "lon": lon - 0.001, "estimated_cost_for_two_inr": 800, "is_cost_estimated": True}
        ]
    }

def save_itinerary(user_id: str, event_id: str, plan_json: str) -> dict:
    """Saves the approved 'Plan My Night' itinerary to the database."""
    try:
        import json
        if isinstance(plan_json, str):
            plan_data = json.loads(plan_json)
        else:
            plan_data = plan_json
        
        result = supabase_admin.table("user_itineraries").insert({
            "user_id": user_id,
            "event_id": event_id,
            "plan_json": plan_data
        }).execute()
        return {"success": True, "message": "Itinerary saved successfully."}
    except Exception as e:
        return {"success": False, "message": f"Failed to save itinerary: {str(e)}"}

def build_itinerary(ticket_price: float, group_size: int, cab_fare: float, restaurant_cost_for_two: float) -> dict:
    """Calculates itinerary totals deterministically."""
    total_ticket_cost = ticket_price * group_size
    # Pro-rate restaurant cost based on cost_for_two
    restaurant_cost = (restaurant_cost_for_two / 2.0) * group_size
    total_cost = total_ticket_cost + cab_fare + restaurant_cost
    
    return {
        "success": True,
        "total_ticket_cost_inr": total_ticket_cost,
        "total_restaurant_cost_inr": restaurant_cost,
        "total_cab_fare_inr": cab_fare,
        "grand_total_inr": total_cost,
        "message": f"Deterministic grand total is INR {total_cost}"
    }

# ---------------------------------------------------------------------------
# Gemini function declarations (JSON schema)
#
# Deliberately no user_id/chat_id parameter on any of these - customer_agent.py
# binds those from the resolved request context, not from the model.
# ---------------------------------------------------------------------------

FUNCTION_DECLARATIONS = [
    {
        "name": "search_events",
        "description": "Use this for upcoming events, concert dates, event locations, ticket availability, prices, or categories. Use it for any 'which concerts/events are available', 'show me X concerts', or 'when is the next X' question.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Artist or event name to search for, e.g. 'Arijit Singh'. Leave empty to just filter by city."},
                "city": {"type": "string", "description": "City to filter by, e.g. 'Mumbai'. Optional."},
                "temporal_intent": {
                    "type": "string",
                    "description": "Optional temporal constraint inferred from the user query.",
                    "enum": ["TODAY", "TOMORROW", "THIS_WEEK", "THIS_WEEKEND", "NEXT_WEEK", "NEXT_WEEKEND", "THIS_MONTH", "NEXT_MONTH", "ALL", "THIS_MONDAY", "THIS_TUESDAY", "THIS_WEDNESDAY", "THIS_THURSDAY", "THIS_FRIDAY", "THIS_SATURDAY", "THIS_SUNDAY", "NEXT_MONDAY", "NEXT_TUESDAY", "NEXT_WEDNESDAY", "NEXT_THURSDAY", "NEXT_FRIDAY", "NEXT_SATURDAY", "NEXT_SUNDAY"]
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
            }
        }
    },
    {
        "name": "get_ticket_categories",
        "description": "Use this to get ticket categories, prices, and seat availability for a specific event. Requires the event_id from search_events.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event_id returned by search_events."}
            },
            "required": ["event_id"]
        }
    },
    {
        "name": "get_available_seats",
        "description": "Use this AFTER get_ticket_categories, before booking, for events that use seat selection (an interactive seat map, like a cinema or stadium). Returns exactly which seats (row + number) are currently open in a category, e.g. 'Row N: 1, 2, 5, 8'. If the result says has_seat_map is false, this event does NOT use seat selection - just ask how many tickets the user wants instead of asking for seat numbers. Call this whenever the user wants to see or choose specific seats, or before confirming a booking so you can mention what's actually available.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event_id to check seats for."},
                "category": {"type": "string", "description": "Optional - limit results to one ticket category."}
            },
            "required": ["event_id"]
        }
    },
    {
        "name": "advise_seats",
        "description": "Get deterministic seat or ticket-category recommendations for a specific event. Use for best/cheap/premium seat queries, price limits, N seats together, or category recommendations. event_id must be resolved from prior search_events. Returns only available seats or \"Any\" for non-seat-map events. Never invent seat numbers.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID (resolved from search_events)."},
                "max_price": {"type": "number", "description": "Optional upper price filter (inclusive)."},
                "category": {"type": "string", "description": "Optional ticket category filter."},
                "quantity": {"type": "integer", "description": "Number of seats desired together.", "default": 1},
                "preference": {"type": "string", "description": "Preference hint: 'cheap', 'best_value', or 'premium'."},
                "max_results": {"type": "integer", "description": "Maximum number of recommendations to return."}
            },
            "required": ["event_id"]
        }
    },
    {
        "name": "book_ticket_transaction",
        "description": "Starts the ticket booking process. NEVER use this before the user explicitly confirms the booking (e.g. 'Yes, proceed', 'Confirm', 'Book it'). NEVER call this just because the user said 'Book 2 VIP tickets' - you must first show the complete booking summary and ask for confirmation. This checks availability, reserves seats, creates the booking as Pending Payment, and returns a Razorpay payment link. This does NOT instantly confirm the booking - you must send the payment_link to the user and clearly tell them the booking is reserved but only confirmed once they complete payment. NEVER claim a booking is confirmed - you only reserve it pending payment.\n\nSEATS: for events where get_available_seats returned has_seat_map=true, ask the user which specific seats they want (e.g. 'N5, N6') and pass them as seat_numbers - or if they say 'any 2 seats' / don't care which, pass seats as a plain count instead and the system will auto-pick available ones. For events where has_seat_map=false (or you haven't checked seats at all), just pass seats as a count - never pass seat_numbers for those events.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event_id of the concert being booked."},
                "category": {"type": "string", "description": "The ticket category, must match get_ticket_categories exactly."},
                "seats": {"type": "integer", "description": "Number of seats to book - use this OR seat_numbers, not both. Required if not using seat_numbers."},
                "seat_numbers": {
                    "type": "array",
                    "description": "Specific seats the user chose, e.g. ['N5', 'N6'] - only for events with has_seat_map=true. Use this OR seats, not both.",
                    "items": {"type": "string"}
                }
            },
            "required": ["event_id", "category"]
        }
    },
    {
        "name": "get_user_booking_history",
        "description": "The source of truth for the user's own previous bookings and booking history. Use this whenever the user asks about previous bookings, booking history, what they booked before, or their past concerts. NEVER answer these from conversation memory - always use this tool. The tool response will tell you the exact total count of matching bookings. Never infer the total count just by looking at the returned array, use the total_count field.",
        "parameters": {
            "type": "object",
            "properties": {
                "temporal_intent": {
                    "type": "string",
                    "description": "Optional temporal constraint inferred from the user query.",
                    "enum": ["TODAY", "TOMORROW", "THIS_WEEK", "THIS_WEEKEND", "NEXT_WEEK", "NEXT_WEEKEND", "THIS_MONTH", "NEXT_MONTH", "ALL", "THIS_MONDAY", "THIS_TUESDAY", "THIS_WEDNESDAY", "THIS_THURSDAY", "THIS_FRIDAY", "THIS_SATURDAY", "THIS_SUNDAY", "NEXT_MONDAY", "NEXT_TUESDAY", "NEXT_WEDNESDAY", "NEXT_THURSDAY", "NEXT_FRIDAY", "NEXT_SATURDAY", "NEXT_SUNDAY"]
                },
                "specific_month": {
                    "type": "integer",
                    "description": "Optional specific month number (1-12) if the user asks for a specific month like 'December'. Only use if a specific month is named."
                }
            }
        }
    },
    {
        "name": "get_user_hosted_shows",
        "description": "Use this whenever the user asks about shows they have hosted, submitted, or listed. This tool is the source of truth for the user's own hosted/submitted shows. NEVER invent or infer this from conversation memory.",
        "parameters": {"type": "object", "properties": {}}
    },
    {
        "name": "check_cancellation_eligibility",
        "description": "Use this to check if a specific booking can be cancelled, and to find out the exact refund amount and cancellation fee percentage. You must ALWAYS use this tool before cancelling a booking to read the refund amount to the user. Do not invent cancellation policies or refund amounts.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "string", "description": "The booking ID to check for cancellation eligibility."}
            },
            "required": ["booking_id"]
        }
    },
    {
        "name": "cancel_booking",
        "description": "Use this ONLY when the user explicitly wants to cancel an existing booking AND has already confirmed they want to proceed after hearing the refund amount. If the booking_id is not known, first call get_user_booking_history to find it. Then call check_cancellation_eligibility to tell the user the refund amount and ask for confirmation. Once they confirm, use this tool to actually cancel the booking. This tool cancels the booking, restores the seats, and automatically initiates the Razorpay refund. Never claim a refund succeeded without checking the tool response.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "string", "description": "The booking ID to cancel."}
            },
            "required": ["booking_id"]
        }
    },
    {
        "name": "link_telegram_account",
        "description": "Links this Telegram chat to an existing website account so the user's bookings, wishlist, and preferences carry over here. ONLY use this when the user explicitly provides the email address they signed up with on the website, and only in a Telegram conversation. Never guess or reuse an email from earlier in the conversation without the user confirming it's the right one for this purpose. Returns linked: true on success, or linked: false with a message if no account matched that email.",
        "parameters": {
            "type": "object",
            "properties": {
                "email": {"type": "string", "description": "The email address the user signed up with on the website."}
            },
            "required": ["email"]
        }
    },
    {
        "name": "get_buy_advice",
        "description": "Use this to get the deterministic 'buy now vs wait' demand signal for a specific event. Returns % sold, days left, and urgency level. NEVER invent these metrics yourself.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID."}
            },
            "required": ["event_id"]
        }
    },
    {
        "name": "maps_directions",
        "description": "Real OSM OSRM directions API to estimate travel distance and time from the event venue to a destination (e.g., restaurant). Returns real driving distance, estimated time, and estimated cab fare.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID to use as the starting location (venue coordinates)."},
                "destination_lat": {"type": "number", "description": "Latitude of the destination (e.g. the selected restaurant)."},
                "destination_lon": {"type": "number", "description": "Longitude of the destination."}
            },
            "required": ["event_id", "destination_lat", "destination_lon"]
        }
    },
    {
        "name": "restaurant_suggestions",
        "description": "Real OSM Overpass API restaurant search near the event venue within a given budget. Returns a list of real nearby restaurants with coordinates.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event ID to search near (uses exact venue coordinates)."},
                "budget_inr": {"type": "number", "description": "Budget in INR for dining. Will filter out overly expensive estimated restaurants."}
            },
            "required": ["event_id"]
        }
    },
    {
        "name": "build_itinerary",
        "description": "Calculates itinerary totals deterministically based on ticket price, group size, cab fare, and restaurant cost.",
        "parameters": {
            "type": "object",
            "properties": {
                "ticket_price": {"type": "number", "description": "Price per ticket"},
                "group_size": {"type": "integer", "description": "Number of people"},
                "cab_fare": {"type": "number", "description": "Estimated cab fare"},
                "restaurant_cost_for_two": {"type": "number", "description": "Restaurant cost for two"}
            },
            "required": ["ticket_price", "group_size", "cab_fare", "restaurant_cost_for_two"]
        }
    },
    {
        "name": "save_itinerary",
        "description": "Use this tool to save a Plan My Night itinerary to the user's account AFTER they explicitly approve it. Do not call this before the user confirms the plan.",
        "parameters": {
            "type": "object",
            "properties": {
                "event_id": {"type": "string", "description": "The event_id associated with this itinerary."},
                "plan_json": {"type": "string", "description": "A JSON-formatted string detailing the full itinerary (event, restaurant, travel, budget)."}
            },
            "required": ["event_id", "plan_json"]
        }
    },
    {
        "name": "request_seat_upgrade",
        "description": "Use this tool when a user wants to upgrade their existing booking to a better category (e.g. VIP), but it is currently sold out. This adds them to the automated monitor which will alert them via Telegram/Email if seats become available.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "string", "description": "The user's existing booking ID to upgrade."},
                "desired_category": {"type": "string", "description": "The target ticket category they want to upgrade to (e.g., 'VIP')."}
            },
            "required": ["booking_id", "desired_category"]
        }
    },
    {
        "name": "approve_seat_upgrade",
        "description": "Use this tool ONLY after the user has received a seat upgrade availability notification and responds in chat saying they want to proceed with the upgrade (e.g., 'Yes, upgrade my tickets' or 'Approve the upgrade'). If the upgrade costs more, it returns a Razorpay payment link. If cheaper, it automatically downgrades and initiates a refund. Tell the user the outcome clearly.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "string", "description": "The user's original booking ID for which they were notified about the upgrade."}
            },
            "required": ["booking_id"]
        }
    },
    {
        "name": "direct_seat_downgrade",
        "description": "Use this tool to immediately downgrade a user's booking to a cheaper ticket category. DO NOT use cancel_booking for downgrades. This tool directly invokes the downgrade workflow, reassigns seats, and processes the Razorpay refund for the price difference.",
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "string", "description": "The existing booking ID to downgrade."},
                "desired_category": {"type": "string", "description": "The target ticket category (must be cheaper than the current one)."}
            },
            "required": ["booking_id", "desired_category"]
        }
    }
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
    "check_cancellation_eligibility": check_cancellation_eligibility,
    "link_telegram_account": link_telegram_account,
    "get_buy_advice": get_buy_advice,
    "advise_seats": advise_seats,
    "maps_directions": maps_directions,
    "restaurant_suggestions": restaurant_suggestions,
    "build_itinerary": build_itinerary,
    "save_itinerary": save_itinerary,
    "request_seat_upgrade": request_seat_upgrade,
    "approve_seat_upgrade": approve_seat_upgrade,
    "direct_seat_downgrade": direct_seat_downgrade,
}