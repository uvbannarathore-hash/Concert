import logging
from datetime import date, datetime
from zoneinfo import ZoneInfo
from app.supabase_client import supabase_admin

logger = logging.getLogger("demand_service")

def get_buy_advice(event_id: str) -> dict:
    """
    Calculates deterministic demand signals for an event.
    """
    try:
        # Fetch event
        event_res = supabase_admin.table("events").select("event_date, status").eq("event_id", event_id).execute()
        if not event_res.data:
            return {"error": "Event not found"}
        
        event = event_res.data[0]
        status = event.get("status", "")
        
        # Check event status
        if status in ["Cancelled", "Completed"]:
            return {
                "event_id": event_id,
                "demand_level": status,
                "available_seats": 0,
                "total_capacity": 0,
                "sold_percentage": 0,
                "sold_seats": 0,
                "days_left": 0,
                "message": f"This event is {status.lower()}."
            }
        
        if status == "Sold Out":
            return {
                "event_id": event_id,
                "demand_level": "Sold Out",
                "available_seats": 0,
                "total_capacity": 0,
                "sold_percentage": 100,
                "sold_seats": 0,
                "days_left": 0,
                "message": "This event is sold out."
            }
            
        # Parse date and calculate days left
        today = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        try:
            event_date = date.fromisoformat(event["event_date"])
            days_left = (event_date - today).days
        except (ValueError, TypeError):
            days_left = -1
            
        if days_left < 0:
            # Past event
            return {
                "event_id": event_id,
                "demand_level": "Past",
                "available_seats": 0,
                "total_capacity": 0,
                "sold_percentage": 0,
                "sold_seats": 0,
                "days_left": days_left,
                "message": "This event has already passed."
            }
            
        # Fetch ticket categories to calculate capacity
        tickets_res = supabase_admin.table("ticket_categories").select("total_seats, available_seats").eq("event_id", event_id).execute()
        
        total_capacity = sum((t.get("total_seats") or 0) for t in tickets_res.data)
        available_seats = sum((t.get("available_seats") or 0) for t in tickets_res.data)
        
        if total_capacity <= 0:
            return {
                "event_id": event_id,
                "demand_level": "Unknown",
                "available_seats": 0,
                "total_capacity": 0,
                "sold_percentage": 0,
                "sold_seats": 0,
                "days_left": days_left,
                "message": "Capacity data unavailable."
            }
            
        sold_seats = total_capacity - available_seats
        sold_percentage = int((sold_seats / total_capacity) * 100)
        
        # Deterministic demand logic
        if sold_percentage >= 80 or (sold_percentage >= 60 and days_left <= 3):
            demand_level = "High"
            message = "Tickets are selling fast. Consider booking now."
        elif sold_percentage >= 40 or (sold_percentage >= 20 and days_left <= 7):
            demand_level = "Medium"
            message = "Demand is moderate. There is still availability."
        else:
            demand_level = "Low"
            message = "There is plenty of availability right now, so there is less urgency."
            
        return {
            "event_id": event_id,
            "sold_percentage": sold_percentage,
            "available_seats": available_seats,
            "total_capacity": total_capacity,
            "sold_seats": sold_seats,
            "days_left": days_left,
            "demand_level": demand_level,
            "message": message
        }
    except Exception as e:
        logger.error(f"Error calculating buy advice for {event_id}: {str(e)}")
        return {"error": "Internal error calculating demand"}
