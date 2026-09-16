import asyncio
import time
import uuid
import sys
import os
from unittest.mock import patch, MagicMock

# Ensure tests can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.supabase_client import supabase_admin
from app.main import app
from app.auth import get_current_user
from app.limiter import limiter
import httpx

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TEST_ID = str(uuid.uuid4())[:8]
TEST_EVENT_ID = f"API_TEST_EVT_{TEST_ID}"
TEST_USER_ID = f"API_TEST_USR_{TEST_ID}"
TEST_CAT_A = f"API_TEST_CAT_A_{TEST_ID}"
TEST_CAT_B = f"API_TEST_CAT_B_{TEST_ID}"

async def _cleanup():
    print("\nCleaning up synthetic API test data...")
    supabase_admin.table("bookings").delete().eq("event_id", TEST_EVENT_ID).execute()
    supabase_admin.table("ticket_categories").delete().eq("event_id", TEST_EVENT_ID).execute()
    supabase_admin.table("events").delete().eq("event_id", TEST_EVENT_ID).execute()
    supabase_admin.table("artists").delete().eq("artist_id", f"API_TEST_ART_{TEST_ID}").execute()
    supabase_admin.table("venues").delete().eq("venue_id", f"API_TEST_VEN_{TEST_ID}").execute()
    try:
        supabase_admin.table("users").delete().eq("user_id", TEST_USER_ID).execute()
    except Exception:
        pass
    print("Cleanup finished.")

async def _setup():
    print(f"Setting up synthetic data for API Load Test: {TEST_EVENT_ID}")
    
    # 1. User
    try:
        supabase_admin.table("users").insert({
            "user_id": TEST_USER_ID,
            "email": "apiloadtest@example.com",
            "name": "API Load Tester",
            "is_admin": False
        }).execute()
    except Exception:
        pass 
        
    # 2. Artist
    supabase_admin.table("artists").insert({
        "artist_id": f"API_TEST_ART_{TEST_ID}",
        "name": f"API Load Test Artist {TEST_ID}"
    }).execute()

    # 3. Venue
    supabase_admin.table("venues").insert({
        "venue_id": f"API_TEST_VEN_{TEST_ID}",
        "name": "API Load Test Arena",
        "city": "Test City"
    }).execute()

    # 4. Event
    supabase_admin.table("events").insert({
        "event_id": TEST_EVENT_ID,
        "artist_id": f"API_TEST_ART_{TEST_ID}",
        "artist_name": "API Concurrency Test Artist",
        "venue_id": f"API_TEST_VEN_{TEST_ID}",
        "venue_name": "API Test Arena",
        "city": "Test City",
        "event_date": "2030-01-01",
        "event_time": "20:00:00",
        "status": "Upcoming",
        "image_url": "http://example.com/img.jpg",
        "description": "API Load Testing Event"
    }).execute()

    # 5. Categories
    supabase_admin.table("ticket_categories").insert({
        "event_id": TEST_EVENT_ID,
        "category": TEST_CAT_A,
        "price_inr": 1000,
        "available_seats": 10,
        "total_seats": 10
    }).execute()

    supabase_admin.table("ticket_categories").insert({
        "event_id": TEST_EVENT_ID,
        "category": TEST_CAT_B,
        "price_inr": 2000,
        "available_seats": 10,
        "total_seats": 10
    }).execute()


async def make_api_booking(client, category, seats):
    """Hits the real FastAPI create-order endpoint via httpx ASG dispatcher."""
    payload = {
        "event_id": TEST_EVENT_ID,
        "category": category,
        "seats": seats
    }
    # No auth header needed because we override get_current_user
    response = await client.post("/bookings/create-order", json=payload)
    if response.status_code == 200:
        return True, response.json()
    else:
        return False, response.json()


async def run_api_test():
    print("\n============================================================")
    print("API LOAD TEST — 50 requests, 10 available seats")
    print("============================================================")
    
    # 1. Override the Authentication dependency
    app.dependency_overrides[get_current_user] = lambda: {"user_id": TEST_USER_ID, "is_admin": False}
    
    # Disable Rate Limiter for test
    original_limiter_state = limiter.enabled
    limiter.enabled = False
    
    # 2. Patch Razorpay to return a fake order ID instantly without hitting the network
    with patch("app.routes.booking_routes.razorpay_client.order.create") as mock_razorpay:
        mock_razorpay.return_value = {"id": "order_mock_123"}
        
        # Use ASGITransport to properly route requests in-memory without sockets
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            start_time = time.time()
            
            # Fire 50 concurrent requests
            tasks = [make_api_booking(client, TEST_CAT_A, 1) for _ in range(50)]
            results = await asyncio.gather(*tasks)
            
            elapsed = time.time() - start_time
            
            successes = sum(1 for r in results if r[0])
            failures = sum(1 for r in results if not r[0])
            
            # Check final DB inventory
            cat = supabase_admin.table("ticket_categories").select("available_seats").eq("event_id", TEST_EVENT_ID).eq("category", TEST_CAT_A).execute()
            final_inventory = cat.data[0]["available_seats"] if cat.data else -1
            
            print(f"Attempts: 50")
            print(f"Successful HTTP 200: {successes}")
            print(f"Failed HTTP 4xx/5xx: {failures}")
            print(f"Final DB Inventory: {final_inventory} (Expected: 0)")
            print(f"Oversold: {'YES' if final_inventory < 0 or successes > 10 else 'NO'}")
            print(f"Elapsed time: {elapsed:.2f}s")
            
            if successes == 10 and failures == 40 and final_inventory == 0:
                print("RESULT: PASS")
            else:
                print("RESULT: FAIL")
                
    # Remove override and restore limiter
    app.dependency_overrides.clear()
    limiter.enabled = original_limiter_state

async def main():
    print(f"Initializing API Load Test... Run ID: {TEST_ID}")
    try:
        await _setup()
        await run_api_test()
    except Exception as e:
        print(f"Test crashed: {e}")
    finally:
        await _cleanup()

if __name__ == "__main__":
    asyncio.run(main())
