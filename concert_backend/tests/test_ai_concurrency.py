import asyncio
import time
import uuid
import sys
import os
from unittest.mock import patch

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

# Generate 10 synthetic test users and sessions
USERS = []
for i in range(10):
    user_id = f"AI_TEST_USR_{TEST_ID}_{i}"
    session_id = f"AI_TEST_SESS_{TEST_ID}_{i}"
    color = f"Color_{TEST_ID}_{i}"
    USERS.append({"user_id": user_id, "session_id": session_id, "color": color})


async def _cleanup():
    print("\nCleaning up synthetic AI test data...")
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
    print(f"Setting up synthetic data for AI Load Test: {TEST_ID}")
    
    # 1. Create dummy users
    for u in USERS:
        try:
            supabase_admin.table("users").insert({
                "user_id": u["user_id"],
                "email": f"ai_loadtest_{u['user_id']}@example.com",
                "name": f"AI Load Tester {i}",
                "is_admin": False
            }).execute()
        except Exception:
            pass 


# ---------------------------------------------------------
# MOCKS
# ---------------------------------------------------------

# Mock Auth Dependency
def mock_get_current_user(x_test_user_id: str = Header(...)):
    """Reads the test user ID from a custom header instead of JWT."""
    return {"user_id": x_test_user_id, "is_admin": False}

# Mock Intent Classification
def mock_classify_intent(message: str, history: list) -> object:
    """Bypass the intent classifier LLM call."""
    from app.agents.customer_agent import IntentClassification
    return IntentClassification(intent="UNKNOWN", context_needed=True)

# Mock Gemini Run Agent
async def mock_run_agent(system_prompt, function_declarations, tool_handlers, history, user_message, **kwargs):
    """Bypasses Gemini API, simulating memory recall logic based on passed history."""
    color_found = None
    # Parse history for color injection
    for content in history:
        for part in content.parts:
            if part.text and "My favorite color is" in part.text:
                color_found = part.text.split("My favorite color is ")[-1].strip(". ")
                
    if "What is my favorite color?" in user_message:
        if color_found:
            return f"Your favorite color is {color_found}."
        else:
            return "I don't know your favorite color."
            
    if "My favorite color is" in user_message:
        color = user_message.split("My favorite color is ")[-1].strip(".] [") 
        # Clean up any suffix that might have gotten caught
        color = color.split()[0]
        return f"Got it, your favorite color is {color}."
        
    return "Mock LLM Response"


async def make_chat_request(client, user_id, session_id, message):
    """Hits the real FastAPI chat endpoint via httpx ASG dispatcher."""
    payload = {
        "message": message,
        "session_id": session_id
    }
    headers = {
        "x-test-user-id": user_id
    }
    response = await client.post("/chat", json=payload, headers=headers)
    if response.status_code == 200:
        return True, response.json()
    else:
        return False, response.text


async def run_ai_test():
    print("\n============================================================")
    print(f"AI LOAD TEST — {len(USERS)} concurrent sessions")
    print("============================================================")
    
    # Override Auth
    app.dependency_overrides[get_current_user] = mock_get_current_user
    
    # Patch the intent classifier and the run_agent functions
    with patch("app.agents.customer_agent.classify_intent", side_effect=mock_classify_intent):
        with patch("app.agents.customer_agent.gemini_loop.run_agent", side_effect=mock_run_agent):
            
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                start_time = time.time()
                
                # PHASE 1: Write to memory concurrently
                print("\n[Phase 1] Concurrently writing unique memory contexts...")
                tasks = []
                for u in USERS:
                    msg = f"My favorite color is {u['color']}."
                    tasks.append(make_chat_request(client, u["user_id"], u["session_id"], msg))
                    
                p1_results = await asyncio.gather(*tasks)
                p1_success = sum(1 for r in p1_results if r[0])
                print(f"Phase 1 Success: {p1_success}/{len(USERS)}")
                
                # PHASE 2: Read from memory concurrently
                print("\n[Phase 2] Concurrently requesting memory recall...")
                tasks = []
                for u in USERS:
                    msg = "What is my favorite color?"
                    tasks.append(make_chat_request(client, u["user_id"], u["session_id"], msg))
                    
                p2_results = await asyncio.gather(*tasks)
                p2_success = sum(1 for r in p2_results if r[0])
                print(f"Phase 2 Success: {p2_success}/{len(USERS)}")
                
                elapsed = time.time() - start_time
                
                # VERIFICATION
                print("\n[Verification] Checking session isolation...")
                isolation_failures = 0
                for i, r in enumerate(p2_results):
                    success, data = r
                    expected_color = USERS[i]["color"]
                    
                    if not success:
                        print(f"User {i} Request Failed: {data}")
                        isolation_failures += 1
                        continue
                        
                    reply = data.get("reply", "")
                    if expected_color not in reply:
                        print(f"ERROR: Session leak or amnesia! User {i} expected '{expected_color}' but got: '{reply}'")
                        isolation_failures += 1
                        
                print(f"\nAttempts: {len(USERS) * 2}")
                print(f"Isolation Failures: {isolation_failures}")
                print(f"Elapsed time: {elapsed:.2f}s")
                
                if p1_success == len(USERS) and p2_success == len(USERS) and isolation_failures == 0:
                    print("RESULT: PASS")
                else:
                    print("RESULT: FAIL")
                
    # Remove override
    app.dependency_overrides.clear()

async def main():
    print(f"Initializing AI Concurrency Test... Run ID: {TEST_ID}")
    try:
        await _setup()
        await run_ai_test()
    except Exception as e:
        print(f"Test crashed: {e}")
    finally:
        await _cleanup()

if __name__ == "__main__":
    asyncio.run(main())
