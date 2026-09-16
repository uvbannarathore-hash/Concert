import asyncio
import time
import uuid
import sys

# Ensure tests can import app modules
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.supabase_client import supabase_admin

# Synthetic IDs that are virtually guaranteed not to collide
TEST_ID = str(uuid.uuid4())[:8]
TEST_EVENT_ID = f"LOAD_TEST_EVENT_{TEST_ID}"
TEST_USER_ID = f"TEST_USER_{TEST_ID}"
TEST_CAT_A = f"LOAD_TEST_CAT_A_{TEST_ID}"
TEST_CAT_B = f"LOAD_TEST_CAT_B_{TEST_ID}"

async def _cleanup():
    """Explicit safe cleanup, assuming NO cascade guarantees."""
    print("\nRunning explicit cleanup of synthetic data...")
    # Delete in reverse dependency order to avoid FK violations
    supabase_admin.table("bookings").delete().eq("event_id", TEST_EVENT_ID).execute()
    supabase_admin.table("ticket_categories").delete().eq("event_id", TEST_EVENT_ID).execute()
    supabase_admin.table("events").delete().eq("event_id", TEST_EVENT_ID).execute()
    supabase_admin.table("artists").delete().eq("artist_id", f"TEST_ARTIST_{TEST_ID}").execute()
    supabase_admin.table("venues").delete().eq("venue_id", f"TEST_VENUE_{TEST_ID}").execute()
    # Users can't be deleted via normal client without admin auth, 
    # but we can try if it's in public.users or just leave the auth.users alone.
    try:
        supabase_admin.table("users").delete().eq("user_id", TEST_USER_ID).execute()
    except Exception:
        pass
    
    # Verification
    events_left = supabase_admin.table("events").select("event_id").eq("event_id", TEST_EVENT_ID).execute()
    if not events_left.data:
        print("Cleanup complete. Zero trace left in database.")
    else:
        print("WARNING: Cleanup failed to remove all test data.")

async def _setup():
    """Create synthetic event, categories, and user."""
    print(f"Setting up synthetic test data for Event: {TEST_EVENT_ID}")
    
    # 1. Create a dummy user
    try:
        supabase_admin.table("users").insert({
            "user_id": TEST_USER_ID,
            "email": "loadtest@example.com",
            "name": "Load Tester",
            "is_admin": False
        }).execute()
    except Exception:
        pass 
        
    # 2. Create the dummy artist
    supabase_admin.table("artists").insert({
        "artist_id": f"TEST_ARTIST_{TEST_ID}",
        "name": f"Load Test Artist {TEST_ID}"
    }).execute()

    # 3. Create the dummy venue
    supabase_admin.table("venues").insert({
        "venue_id": f"TEST_VENUE_{TEST_ID}",
        "name": "Load Test Arena",
        "city": "Test City"
    }).execute()

    # 4. Create the dummy event
    supabase_admin.table("events").insert({
        "event_id": TEST_EVENT_ID,
        "artist_id": f"TEST_ARTIST_{TEST_ID}",
        "artist_name": "Concurrency Test Artist",
        "venue_id": f"TEST_VENUE_{TEST_ID}",
        "venue_name": "Test Arena",
        "city": "Test City",
        "event_date": "2030-01-01",
        "event_time": "20:00:00",
        "status": "Upcoming",
        "image_url": "http://example.com/img.jpg",
        "description": "Load Testing Event"
    }).execute()

    # 5. Create dummy categories
    # Category A: 10 seats
    supabase_admin.table("ticket_categories").insert({
        "event_id": TEST_EVENT_ID,
        "category": TEST_CAT_A,
        "price_inr": 1000,
        "available_seats": 10,
        "total_seats": 10
    }).execute()

    # Category B: 10 seats (for isolation test)
    supabase_admin.table("ticket_categories").insert({
        "event_id": TEST_EVENT_ID,
        "category": TEST_CAT_B,
        "price_inr": 2000,
        "available_seats": 10,
        "total_seats": 10
    }).execute()


async def make_booking_request(category: str, seats: int):
    """Hits the book_ticket_transaction RPC directly."""
    booking_id = f"BK_TEST_{uuid.uuid4().hex[:8]}"
    try:
        # We use asyncio.to_thread because the supabase-py client is synchronous
        result = await asyncio.to_thread(
            supabase_admin.rpc(
                "book_ticket_transaction",
                {
                    "p_booking_id": booking_id,
                    "p_user_id": TEST_USER_ID,
                    "p_event_id": TEST_EVENT_ID,
                    "p_category": category,
                    "p_seats_booked": seats,
                },
            ).execute
        )
        return True, result.data
    except Exception as e:
        return False, str(e)


async def run_test_1():
    print("\n============================================================")
    print("TEST 1 — OVERSOLD INVENTORY")
    print("============================================================")
    
    start_time = time.time()
    # 50 concurrent requests for 1 seat each (10 available)
    tasks = [make_booking_request(TEST_CAT_A, 1) for _ in range(50)]
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    
    successes = sum(1 for r in results if r[0])
    failures = sum(1 for r in results if not r[0])
    
    # Check final inventory
    cat = supabase_admin.table("ticket_categories").select("available_seats").eq("event_id", TEST_EVENT_ID).eq("category", TEST_CAT_A).execute()
    final_inventory = cat.data[0]["available_seats"] if cat.data else -1
    
    print(f"Attempts: 50")
    print(f"Requested seats: 50")
    print(f"Successful transactions: {successes}")
    print(f"Failed transactions: {failures}")
    print(f"Final inventory: {final_inventory}")
    print(f"Oversold: {'YES' if final_inventory < 0 or successes > 10 else 'NO'}")
    print(f"Negative inventory: {'YES' if final_inventory < 0 else 'NO'}")
    print(f"Elapsed time: {elapsed:.2f}s")
    
    if successes == 10 and failures == 40 and final_inventory == 0:
        print("PASS")
    else:
        print("FAIL")


async def run_test_2():
    print("\n============================================================")
    print("TEST 2 — BULK CONCURRENCY")
    print("============================================================")
    
    # Reset category A to 5 seats
    supabase_admin.table("ticket_categories").update({"available_seats": 5}).eq("event_id", TEST_EVENT_ID).eq("category", TEST_CAT_A).execute()
    
    start_time = time.time()
    # 3 concurrent requests for 3 seats each (5 available)
    tasks = [make_booking_request(TEST_CAT_A, 3) for _ in range(3)]
    results = await asyncio.gather(*tasks)
    
    elapsed = time.time() - start_time
    
    successes = sum(1 for r in results if r[0])
    failures = sum(1 for r in results if not r[0])
    
    cat = supabase_admin.table("ticket_categories").select("available_seats").eq("event_id", TEST_EVENT_ID).eq("category", TEST_CAT_A).execute()
    final_inventory = cat.data[0]["available_seats"]
    
    print(f"Attempts: 3")
    print(f"Requested seats per request: 3 (Total 9)")
    print(f"Successful transactions: {successes}")
    print(f"Failed transactions: {failures}")
    print(f"Final inventory: {final_inventory}")
    
    if successes == 1 and failures == 2 and final_inventory == 2:
        print("PASS")
    else:
        print("FAIL")


async def run_test_3():
    print("\n============================================================")
    print("TEST 3 — CATEGORY ISOLATION")
    print("============================================================")
    
    # Reset both to 10
    supabase_admin.table("ticket_categories").update({"available_seats": 10}).eq("event_id", TEST_EVENT_ID).eq("category", TEST_CAT_A).execute()
    supabase_admin.table("ticket_categories").update({"available_seats": 10}).eq("event_id", TEST_EVENT_ID).eq("category", TEST_CAT_B).execute()
    
    start_time = time.time()
    tasks_a = [make_booking_request(TEST_CAT_A, 1) for _ in range(10)]
    tasks_b = [make_booking_request(TEST_CAT_B, 1) for _ in range(10)]
    
    # Interleave them
    tasks = tasks_a + tasks_b
    import random
    random.shuffle(tasks)
    
    results = await asyncio.gather(*tasks)
    elapsed = time.time() - start_time
    
    cat_a = supabase_admin.table("ticket_categories").select("available_seats").eq("event_id", TEST_EVENT_ID).eq("category", TEST_CAT_A).execute().data[0]["available_seats"]
    cat_b = supabase_admin.table("ticket_categories").select("available_seats").eq("event_id", TEST_EVENT_ID).eq("category", TEST_CAT_B).execute().data[0]["available_seats"]
    
    print(f"Total concurrent requests: 20")
    print(f"Category A final inventory: {cat_a} (Expected: 0)")
    print(f"Category B final inventory: {cat_b} (Expected: 0)")
    print(f"Elapsed time: {elapsed:.2f}s")
    
    if cat_a == 0 and cat_b == 0:
        print("PASS")
    else:
        print("FAIL")


async def main():
    print(f"Initializing Load Test... Run ID: {TEST_ID}")
    try:
        await _setup()
        await run_test_1()
        await run_test_2()
        await run_test_3()
    except Exception as e:
        print(f"Test crashed: {e}")
    finally:
        await _cleanup()

if __name__ == "__main__":
    asyncio.run(main())
