import asyncio
from datetime import datetime, timedelta, timezone
import os
import json
from dotenv import load_dotenv
from google import genai
from pydantic import BaseModel
from groq import Groq

load_dotenv()

import logging
from app.logger import request_id_var, agent_name_var
import uuid

logger = logging.getLogger("pricing_agent")
from app.supabase_client import supabase_admin
from app.config import GEMINI_API_KEY
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

class PricingRecommendation(BaseModel):
    suggested_price_inr: float
    justification: str

def parse_event_datetime(date_str: str, time_str: str) -> datetime:
    dt_str = f"{date_str} {time_str}"
    ist_tz = timezone(timedelta(hours=5, minutes=30))
    try:
        dt_naive = datetime.strptime(dt_str, "%Y-%m-%d %I:%M %p")
    except ValueError:
        dt_naive = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    return dt_naive.replace(tzinfo=ist_tz)

def generate_recommendation(prompt: str) -> dict:
    import time
    
    agent_name_var.set("pricing_agent")
    if not request_id_var.get():
        request_id_var.set(str(uuid.uuid4()))
        
    # 1. Gemini
    if GEMINI_API_KEY:
        client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Starting Gemini attempt 1/1")
        start_time = time.perf_counter()
        try:
            response = client.models.generate_content(
                model='gemini-3.7-flash',
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": PricingRecommendation,
                    "temperature": 0.2
                }
            )
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info("Gemini recommendation generated successfully", extra={"extra_data": {"llm_latency_ms": latency_ms, "model": "gemini-3.7-flash"}})
            return json.loads(response.text)
        except Exception as e:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            err_msg = str(e).lower()
            if "503" in err_msg or "unavailable" in err_msg or "too many requests" in err_msg:
                logger.warning(f"Gemini unavailable. Skipping retries. Error: {e}", extra={"extra_data": {"llm_latency_ms": latency_ms, "fallback_trigger": "503/429"}})
            else:
                logger.warning(f"Gemini failed: {e}", extra={"extra_data": {"llm_latency_ms": latency_ms, "fallback_trigger": "unknown_error"}})

    # 2. Groq fallback
    if GROQ_API_KEY:
        logger.info("Switching to Groq fallback")
        start_time = time.perf_counter()
        groq_client = Groq(api_key=GROQ_API_KEY)
        try:
            groq_prompt = prompt + "\n\nRespond with ONLY a JSON object containing 'suggested_price_inr' (number) and 'justification' (string)."
            response = groq_client.chat.completions.create(
                model="openai/gpt-oss-20b",
                messages=[{"role": "user", "content": groq_prompt}],
                response_format={"type": "json_object"},
                temperature=0.2
            )
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info("Groq recommendation generated successfully", extra={"extra_data": {"llm_latency_ms": latency_ms, "model": "openai/gpt-oss-20b"}})
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(f"Groq fallback failed: {e}", extra={"extra_data": {"llm_latency_ms": latency_ms}})
            
    return None

async def main():
    print("Running Dynamic Pricing Suggestion Agent...")
    
    if not GEMINI_API_KEY and not GROQ_API_KEY:
        print("Both GEMINI_API_KEY and GROQ_API_KEY are missing.")
        return
    
    now = datetime.now(timezone.utc)
    target_start = now + timedelta(hours=72)
    forty_eight_hours_ago = now - timedelta(hours=48)
    twenty_four_hours_ago = now - timedelta(hours=24)
    
    try:
        # Fetch events > 72 hours away
        date_start_str = target_start.strftime("%Y-%m-%d")
        
        events_res = supabase_admin.table("events").select("*").eq("status", "Upcoming").gte("event_date", date_start_str).execute()
        if not events_res.data:
            print("No upcoming events > 72h found.")
            return
            
        eligible_events = []
        for evt in events_res.data:
            try:
                evt_dt = parse_event_datetime(evt["event_date"], evt["event_time"])
                
                if evt_dt > target_start:
                    eligible_events.append({
                        "event": evt,
                        "event_dt": evt_dt
                    })
            except Exception as e:
                print(f"Skipping event {evt.get('event_id')} due to datetime parse error: {e}")
                
        if not eligible_events:
            print("No events exactly > 72h away after precise parsing.")
            return

        admin_history_res = supabase_admin.table("admin_chat_history").select("admin_user_id, session_id").order("created_at", desc=True).limit(1).execute()
        
        for item in eligible_events:
            evt = item["event"]
            evt_dt = item["event_dt"]
            event_id = evt["event_id"]
            
            # Fetch ticket categories
            cats_res = supabase_admin.table("ticket_categories").select("*").eq("event_id", event_id).execute()
            if not cats_res.data:
                continue
                
            for cat in cats_res.data:
                category = cat["category"]
                total_seats = cat["total_seats"]
                available_seats = cat["available_seats"]
                price_inr = float(cat["price_inr"])
                last_alert_at = cat.get("last_pricing_alert_at")
                
                # Check 80% capacity condition
                if total_seats == 0:
                    continue
                    
                if available_seats > total_seats * 0.20:
                    continue
                    
                # Check cooldown (24 hours) statically before proceeding
                if last_alert_at:
                    last_alert_dt = datetime.fromisoformat(last_alert_at.replace("Z", "+00:00"))
                    if last_alert_dt > twenty_four_hours_ago:
                        print(f"Cooldown active for event {event_id} category {category}.")
                        continue
                        
                # Check admin session BEFORE expensive operations (Fix #1)
                if not admin_history_res.data:
                    print("No admin chat sessions found to inject notification. Skipping.")
                    continue
                
                # Calculate booking velocity in the last 48 hours
                bookings_res = supabase_admin.table("bookings").select("seats_booked") \
                    .eq("event_id", event_id) \
                    .eq("category", category) \
                    .eq("status", "Confirmed") \
                    .eq("payment_status", "Paid") \
                    .gte("created_at", forty_eight_hours_ago.isoformat()) \
                    .execute()
                    
                velocity_seats = sum(b["seats_booked"] for b in bookings_res.data) if bookings_res.data else 0
                
                percent_full = ((total_seats - available_seats) / total_seats) * 100
                print(f"Event {event_id} Category {category} is {percent_full:.1f}% full. Velocity: {velocity_seats} seats in 48h.")
                
                days_remaining = (evt_dt - now).days
                
                prompt = f"""
                You are a dynamic pricing expert for live events.
                Event: {evt.get('artist_name')} at {evt.get('venue_name')}, {evt.get('city')}
                Category: {category}
                Current Price: ₹{price_inr}
                Total Capacity: {total_seats}
                Remaining Seats: {available_seats}
                Days Remaining Until Event: {days_remaining}
                Booking Velocity: {velocity_seats} tickets sold in the last 48 hours.
                
                Based on high demand (>= 80% sold) and the current booking velocity, suggest a new increased ticket price. 
                Keep the increase reasonable (typically 10-30% depending on velocity and remaining time). 
                Return a logical justification for your pricing. 
                IMPORTANT: The suggested price MUST be higher than the current price, must be a sensible whole number in INR, and cannot be negative.
                """
                
                rec = generate_recommendation(prompt)
                
                if not rec:
                    print(f"Failed to generate recommendation for {event_id}. Both providers failed.")
                    continue
                    
                try:
                    new_price = float(rec["suggested_price_inr"])
                    justification = rec["justification"]
                except Exception as e:
                    print(f"Failed to parse LLM response for {event_id}: {e}")
                    continue
                
                # Fix #3: Server-side pricing guardrail
                if not new_price.is_integer() or new_price <= 0:
                    print(f"Rejected: suggested price {new_price} must be a positive whole INR amount.")
                    continue
                    
                new_price_int = int(new_price)
                min_allowed = int(round(price_inr * 1.10))
                max_allowed = int(round(price_inr * 1.30))
                    
                if new_price_int <= price_inr:
                    print(f"Rejected: suggested price {new_price_int} is not greater than current {price_inr}.")
                    continue
                    
                if new_price_int < min_allowed:
                    print(f"Rejected: suggested price {new_price_int} must be >= 10% higher than current {price_inr} (min {min_allowed}).")
                    continue
                    
                if new_price_int > max_allowed:
                    print(f"Rejected: suggested price {new_price_int} exceeds 30% maximum increase over current {price_inr} (max {max_allowed}).")
                    continue
                    
                print(f"AI Suggests ₹{new_price_int} for {category} (Current: ₹{price_inr}). Justification: {justification}")
                
                # Fix #2: Atomic database-side claim/update
                # Ensure no other agent instance processes this simultaneously
                twenty_four_hours_ago_str = twenty_four_hours_ago.isoformat()
                claim_res = supabase_admin.table("ticket_categories") \
                    .update({"last_pricing_alert_at": now.isoformat()}) \
                    .eq("id", cat["id"]) \
                    .or_(f"last_pricing_alert_at.is.null,last_pricing_alert_at.lt.{twenty_four_hours_ago_str}") \
                    .execute()
                    
                if not claim_res.data:
                    print(f"Concurrency claim failed: another instance already generated an alert for {category}.")
                    continue
                
                # Fix #1: Insert to admin_chat_history only after claim, and revert if insert fails
                recent_admin = admin_history_res.data[0]
                admin_id = recent_admin["admin_user_id"]
                session_id = recent_admin["session_id"]
                
                try:
                    insert_res = supabase_admin.table("pricing_notifications").insert({
                        "admin_user_id": admin_id,
                        "event_id": event_id,
                        "category": category,
                        "percent_full": float(percent_full),
                        "remaining_seats": available_seats,
                        "days_remaining": days_remaining,
                        "velocity_seats": velocity_seats,
                        "current_price": price_inr,
                        "suggested_price": new_price_int,
                        "justification": justification
                    }).execute()
                    
                    if not insert_res.data:
                        raise Exception("Empty response from database during insert.")
                        
                    print(f"Successfully created pricing notification for {category}.")
                except Exception as e:
                    print(f"Failed to create pricing notification for {category}: {e}")
                    # Revert the atomic claim so the next scheduled run can retry
                    revert_val = last_alert_at if last_alert_at else None
                    supabase_admin.table("ticket_categories").update({
                        "last_pricing_alert_at": revert_val
                    }).eq("id", cat["id"]).execute()
                    print(f"Reverted cooldown claim for {category} due to chat insert failure.")
                
    except Exception as e:
        print(f"Error running pricing agent: {e}")

if __name__ == "__main__":
    asyncio.run(main())
