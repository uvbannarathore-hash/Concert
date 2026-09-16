from app.supabase_client import supabase_admin
from collections import defaultdict
from datetime import datetime, timedelta
import pytz

def _get_all_bookings_with_events():
    # We fetch all bookings and their joined event details.
    # We use supabase_admin to bypass RLS.
    res = supabase_admin.table("bookings").select("*, events(*), payments(*)").execute()
    return res.data or []

def get_overview_metrics():
    bookings = _get_all_bookings_with_events()
    
    total_revenue = 0.0
    successful_bookings_count = 0
    total_tickets_sold = 0
    cancelled_count = 0
    
    for b in bookings:
        status = b.get("status")
        payment_status = b.get("payment_status")
        
        if status == "Cancelled":
            cancelled_count += 1
            
        if status == "Confirmed" and payment_status == "Paid":
            successful_bookings_count += 1
            total_tickets_sold += int(b.get("seats_booked") or 0)
            
            payments = b.get("payments") or []
            for p in payments:
                if p.get("status") == "Success":
                    total_revenue += float(p.get("amount") or 0.0)
            
    cancellation_rate = 0.0
    total_valid = cancelled_count + successful_bookings_count
    if total_valid > 0:
        cancellation_rate = (cancelled_count / total_valid) * 100
        
    # Get upcoming events count
    today_str = datetime.now(pytz.timezone('Asia/Kolkata')).strftime("%Y-%m-%d")
    events_res = supabase_admin.table("events").select("event_id").gte("event_date", today_str).execute()
    upcoming_events = len(events_res.data) if events_res.data else 0

    return {
        "total_revenue": total_revenue,
        "total_bookings": successful_bookings_count,
        "total_tickets_sold": total_tickets_sold,
        "upcoming_events": upcoming_events,
        "cancellation_rate": round(cancellation_rate, 2)
    }

def _get_30_day_buckets():
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    return { (now - timedelta(days=i)).strftime('%Y-%m-%d'): 0.0 for i in range(29, -1, -1) }

def _parse_to_ist_date(utc_date_str: str) -> str:
    if not utc_date_str:
        return ""
    try:
        dt = datetime.fromisoformat(utc_date_str.replace('Z', '+00:00'))
        return dt.astimezone(pytz.timezone('Asia/Kolkata')).strftime('%Y-%m-%d')
    except Exception:
        return utc_date_str.split('T')[0]

def get_revenue_over_time():
    bookings = _get_all_bookings_with_events()
    daily_revenue = _get_30_day_buckets()
    
    for b in bookings:
        if b.get("status") == "Confirmed" and b.get("payment_status") == "Paid":
            date_str = _parse_to_ist_date(b.get("created_at", ""))
            if date_str in daily_revenue:
                payments = b.get("payments") or []
                for p in payments:
                    if p.get("status") == "Success":
                        daily_revenue[date_str] += float(p.get("amount") or 0.0)
                
    sorted_data = [{"date": k, "revenue": v} for k, v in sorted(daily_revenue.items())]
    return {"data": sorted_data}

def get_bookings_over_time():
    bookings = _get_all_bookings_with_events()
    daily_bookings = {k: 0 for k in _get_30_day_buckets()}
    
    for b in bookings:
        if b.get("status") == "Confirmed" and b.get("payment_status") == "Paid":
            date_str = _parse_to_ist_date(b.get("created_at", ""))
            if date_str in daily_bookings:
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
