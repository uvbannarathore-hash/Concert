import asyncio
import time
from app.agents import customer_agent
from app.supabase_client import supabase_admin

async def main():
    # We will just test the classify_intent function directly first
    from app.agents.customer_agent import classify_intent
    from google.genai import types
    
    test_cases = [
        "Who is the national bird of India?",
        "What is the capital of France?",
        "Find Bollywood concerts",
        "Events in Mumbai this weekend",
        "Cheap tickets",
        "What are my bookings this month?",
        "What shows have I hosted?",
    ]
    
    print("=== ZERO HISTORY TESTS ===")
    for q in test_cases:
        res = classify_intent(q, [])
        print(f"Q: {q}\nIntent: {res.intent}, Context needed: {res.context_needed}\n")
        time.sleep(4)

    print("=== HISTORY TESTS ===")
    h1 = [types.Content(role="user", parts=[types.Part.from_text(text="Find Arijit Singh concerts in Mumbai")])]
    
    q1 = "Which one is cheaper?"
    res1 = classify_intent(q1, h1)
    print(f"H1 -> Q: {q1}\nIntent: {res1.intent}, Context needed: {res1.context_needed}\n")
    time.sleep(4)
    
    q2 = "What are my bookings this month?"
    res2 = classify_intent(q2, h1)
    print(f"H1 -> Q: {q2}\nIntent: {res2.intent}, Context needed: {res2.context_needed}\n")
    time.sleep(4)

    h2 = [types.Content(role="user", parts=[types.Part.from_text(text="What shows have I hosted?")])]
    q3 = "Which one is upcoming?"
    res3 = classify_intent(q3, h2)
    print(f"H2 -> Q: {q3}\nIntent: {res3.intent}, Context needed: {res3.context_needed}\n")
    
if __name__ == "__main__":
    asyncio.run(main())
