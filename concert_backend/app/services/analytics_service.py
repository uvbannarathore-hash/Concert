from app.supabase_client import supabase_admin
from collections import defaultdict
from datetime import datetime

def _get_all_bookings_with_events():
    # We fetch all bookings and their joined event details.
    # We use supabase_admin to bypass RLS.
    res = supabase_admin.table("bookings").select("*, events(*), payments(*)").execute()
    return res.data or []

def get_overview_metrics():
    bookings = _get_all_bookings_with_events()
    
    total_revenue = 0.0
    total_bookings = 0
    total_tickets_sold = 0
    cancelled_count = 0
    
    for b in bookings:
        status = b.get("status")
        payment_status = b.get("payment_status")
        
        # Count all bookings for cancellation rate denominator
        total_bookings += 1
        
        if status == "Cancelled":
            cancelled_count += 1
            
        if status == "Confirmed" and payment_status == "Paid":
            # Bookings and tickets count for all Confirmed & Paid
            total_tickets_sold += int(b.get("seats_booked") or 0)
            
            # Revenue comes ONLY from successful payments
            payments = b.get("payments") or []
            for p in payments:
                if p.get("status") == "Success":
                    total_revenue += float(p.get("amount") or 0.0)
            
    cancellation_rate = 0.0
    if total_bookings > 0:
        cancellation_rate = (cancelled_count / total_bookings) * 100
        
    # Get upcoming events count
    # Count events where status = 'Upcoming' OR event_date >= today
    today_str = datetime.now().strftime("%Y-%m-%d")
    events_res = supabase_admin.table("events").select("event_id").gte("event_date", today_str).execute()
    upcoming_events = len(events_res.data) if events_res.data else 0

    return {
        "total_revenue": total_revenue,
        "total_bookings": total_bookings,
        "total_tickets_sold": total_tickets_sold,
        "upcoming_events": upcoming_events,
        "cancellation_rate": round(cancellation_rate, 2)
    }

def get_revenue_over_time():
    bookings = _get_all_bookings_with_events()
    daily_revenue = defaultdict(float)
    
    for b in bookings:
        if b.get("status") == "Confirmed" and b.get("payment_status") == "Paid":
            # Use booking date for revenue time series
            date_str = b.get("created_at", "").split("T")[0]
            if date_str:
                payments = b.get("payments") or []
                for p in payments:
                    if p.get("status") == "Success":
                        daily_revenue[date_str] += float(p.get("amount") or 0.0)
                
    # Sort by date
    sorted_data = [{"date": k, "revenue": v} for k, v in sorted(daily_revenue.items())]
    return {"data": sorted_data}

def get_bookings_over_time():
    bookings = _get_all_bookings_with_events()
    daily_bookings = defaultdict(int)
    
    for b in bookings:
        if b.get("status") == "Confirmed" and b.get("payment_status") == "Paid":
            date_str = b.get("created_at", "").split("T")[0]
            if date_str:
                daily_bookings[date_str] += 1
                
    sorted_data = [{"date": k, "bookings": v} for k, v in sorted(daily_bookings.items())]
    return {"data": sorted_data}

def get_top_events(limit: int = 5):
    bookings = _get_all_bookings_with_events()
    events_stats = defaultdict(lambda: {"revenue": 0.0, "tickets_sold": 0, "event_name": ""})
    
    for b in bookings:
        if b.get("status") == "Confirmed" and b.get("payment_status") == "Paid":
            event_id = b.get("event_id")
            event_data = b.get("events") or {}
            event_name = event_data.get("artist_name") or f"Event {event_id}"
            
            events_stats[event_id]["event_name"] = event_name
            events_stats[event_id]["tickets_sold"] += int(b.get("seats_booked") or 0)
            
            payments = b.get("payments") or []
            for p in payments:
                if p.get("status") == "Success":
                    events_stats[event_id]["revenue"] += float(p.get("amount") or 0.0)
            
    # Sort by revenue descending
    sorted_events = sorted(
        [{"event_id": k, **v} for k, v in events_stats.items()],
        key=lambda x: x["revenue"],
        reverse=True
    )
    
    return {"data": sorted_events[:limit]}

def get_category_sales():
    bookings = _get_all_bookings_with_events()
    category_stats = defaultdict(lambda: {"revenue": 0.0, "tickets_sold": 0})
    
    for b in bookings:
        if b.get("status") == "Confirmed" and b.get("payment_status") == "Paid":
            cat = b.get("category") or "Unknown"
            category_stats[cat]["tickets_sold"] += int(b.get("seats_booked") or 0)
            
            payments = b.get("payments") or []
            for p in payments:
                if p.get("status") == "Success":
                    category_stats[cat]["revenue"] += float(p.get("amount") or 0.0)
            
    sorted_cats = [{"category": k, **v} for k, v in sorted(category_stats.items())]
    return {"data": sorted_cats}
