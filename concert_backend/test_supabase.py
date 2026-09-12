import asyncio
from app.supabase_client import supabase_admin

def test():
    users = supabase_admin.table("users").select("user_id").limit(1).execute()
    if not users.data: return
    user_id = users.data[0]["user_id"]
    
    # Test inner join filtering
    bookings = (
        supabase_admin.table("bookings")
        .select("booking_id, events!inner(artist_name, event_date)")
        .eq("user_id", user_id)
        .gte("events.event_date", "2026-09-01")
        .lte("events.event_date", "2026-09-30")
        .execute()
    )
    print("Filtered Bookings:", bookings.data)

if __name__ == "__main__":
    test()
