from datetime import datetime, timezone, timedelta
import logging
from app.supabase_client import supabase_admin

logger = logging.getLogger("event_status_service")

def check_and_update_event_status(events: list) -> list:
    ist = timezone(timedelta(hours=5, minutes=30))
    now = datetime.now(ist)
    
    for evt in events:
        if evt.get("status") in ("Cancelled", "Completed"):
            continue
            
        try:
            dt_str = f"{evt['event_date']} {evt['event_time']}"
            if "AM" in dt_str.upper() or "PM" in dt_str.upper():
                evt_dt = datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p").replace(tzinfo=ist)
            else:
                evt_dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M").replace(tzinfo=ist)
                
            if now > evt_dt:
                evt["status"] = "Completed"
                # Lazy-update DB to propagate status to other systems (agents, etc) safely
                try:
                    supabase_admin.table("events").update({"status": "Completed"}).eq("event_id", evt["event_id"]).execute()
                except Exception as db_err:
                    logger.error(f"Failed to update event {evt['event_id']} status to Completed: {db_err}")
        except Exception as e:
            logger.warning(f"Failed to parse datetime for event {evt.get('event_id')}: {e}")
            
    return events
