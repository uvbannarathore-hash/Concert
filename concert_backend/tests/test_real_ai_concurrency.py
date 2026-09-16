import asyncio
import time
import uuid
import sys
import os

# Ensure tests can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app.supabase_client import supabase_admin
from app.main import app
from app.auth import get_current_user
import httpx
from fastapi import Header

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

TEST_ID = str(uuid.uuid4())[:8]

# Generate 5 synthetic test users and sessions
USERS = []
for i in range(5):
    user_id = f"REAL_AI_USR_{TEST_ID}_{i}"
    session_id = f"REAL_AI_SESS_{TEST_ID}_{i}"
    test_name = f"TesterName{TEST_ID}x{i}"
    USERS.append({"user_id": user_id, "session_id": session_id, "name": test_name})


async def _cleanup():
    print("\nCleaning up synthetic Real AI test data...")
    # Clean chat_history and users
    for u in USERS:
        supabase_admin.table("chat_history").delete().eq("user_id", u["user_id"]).execute()
        
    for u in USERS:
        try:
            supabase_admin.table("users").delete().eq("user_id", u["user_id"]).execute()
        except Exception:
            pass
            
    print("Cleanup finished.")

async def _setup():
    print(f"Setting up synthetic data for Real AI Load Test: {TEST_ID}")
    
    # 1. Create dummy users
    for u in USERS:
        try:
            supabase_admin.table("users").insert({
                "user_id": u["user_id"],
                "email": f"real_ai_{u['user_id']}@example.com",
                "name": u["name"],
                "is_admin": False
            }).execute()
        except Exception:
            pass 


# ---------------------------------------------------------
# MOCKS
# ---------------------------------------------------------

# Mock Auth Dependency
def mock_get_current_user(x_test_user_id: str = Header(...)):
    """Reads the test user ID from a custom header and returns the user dict with the unique name."""
    # Find the corresponding synthetic user's name
    user_name = "DefaultName"
    for u in USERS:
        if u["user_id"] == x_test_user_id:
            user_name = u["name"]
            break
            
    return {"user_id": x_test_user_id, "name": user_name, "is_admin": False}


async def make_chat_request(client, user_id, session_id, message):
    """Hits the real FastAPI chat endpoint via httpx ASGI dispatcher."""
    payload = {
        "message": message,
        "session_id": session_id
    }
    headers = {
        "x-test-user-id": user_id
    }
    response = await client.post("/chat", json=payload, headers=headers, timeout=60.0)
    if response.status_code == 200:
        return True, response.json()
    else:
        return False, response.text


async def run_real_ai_test():
    print("\n============================================================")
    print(f"REAL AI CONCURRENCY TEST — {len(USERS)} concurrent sessions")
    print("============================================================")
    
    # Override Auth to inject our synthetic users (and their unique names)
    app.dependency_overrides[get_current_user] = mock_get_current_user
    
    # NO OTHER MOCKS. We hit the real Intent Classifier and real Gemini models.
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        start_time = time.time()
        
        # We ask a question that requires searching the database so it falls through to Gemini.
        # We explicitly ask the agent to use our name to verify session isolation.
        print("\nFiring concurrent requests to real Gemini API...")
        tasks = []
        for u in USERS:
            # The name is injected via the system prompt context [User name: ...].
            # We prompt it to look up concerts so it doesn't get short-circuited as a GREETING or OUT_OF_DOMAIN.
            msg = f"Can you check if there are any upcoming concerts? Please make sure to greet me by my name in your response so I know you're talking to me."
            tasks.append(make_chat_request(client, u["user_id"], u["session_id"], msg))
            
        results = await asyncio.gather(*tasks)
        success_count = sum(1 for r in results if r[0])
        
        elapsed = time.time() - start_time
        
        # VERIFICATION
        print("\n[Verification] Checking session isolation and response integrity...")
        isolation_failures = 0
        
        for i, r in enumerate(results):
            success, data = r
            expected_name = USERS[i]["name"]
            
            if not success:
                print(f"User {i} Request Failed (HTTP Error): {data}")
                isolation_failures += 1
                continue
                
            reply = data.get("reply", "")
            print(f"\n--- User {i} ({expected_name}) ---")
            print(f"Reply Preview: {reply[:150]}...")
            
            # Verify the expected name is in the response
            if expected_name.lower() not in reply.lower():
                print(f"ERROR: Expected name '{expected_name}' not found in reply!")
                isolation_failures += 1
                
            # Verify NO OTHER user's name leaked into this response
            for j, other_u in enumerate(USERS):
                if i != j:
                    if other_u["name"].lower() in reply.lower():
                        print(f"SEVERE LEAK: Found User {j}'s name ('{other_u['name']}') in User {i}'s reply!")
                        isolation_failures += 1
                        
        print(f"\nAttempts: {len(USERS)}")
        print(f"Successful 200 OK: {success_count}/{len(USERS)}")
        print(f"Cross-Contamination / Isolation Failures: {isolation_failures}")
        print(f"Total Elapsed Time: {elapsed:.2f}s")
        
        if success_count == len(USERS) and isolation_failures == 0:
            print("RESULT: PASS")
        else:
            print("RESULT: FAIL")
            
    # Remove override
    app.dependency_overrides.clear()

async def main():
    print(f"Initializing REAL AI Concurrency Test... Run ID: {TEST_ID}")
    try:
        await _setup()
        await run_real_ai_test()
    except Exception as e:
        print(f"Test crashed: {e}")
    finally:
        await _cleanup()

if __name__ == "__main__":
    asyncio.run(main())
