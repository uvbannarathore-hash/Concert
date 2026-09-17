import logging
import asyncio
from fastapi import APIRouter, HTTPException, Body, Depends, Request
from pydantic import BaseModel
from typing import List, Optional

from app.supabase_client import supabase_anon
from app.services.embedding_service import generate_query_embedding
from app.services.event_status_service import check_and_update_event_status
from app.auth import get_current_user

logger = logging.getLogger("ai_routes")

router = APIRouter(prefix="/ai", tags=["ai"])

class SearchRequest(BaseModel):
    query: str

class SearchResponse(BaseModel):
    results: List[dict]

@router.get("/events/{event_id}/buy-advice")
def get_buy_advice_endpoint(event_id: str):
    from app.services.demand_service import get_buy_advice
    result = get_buy_advice(event_id)
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result

@router.post("/search", response_model=SearchResponse)
async def search_events(payload: SearchRequest, request: Request):
    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
        
    if len(query) > 500:
        query = query[:500]
        
    try:
        # Check if already disconnected before we even start
        if await request.is_disconnected():
            logger.info("Search request cancelled before starting")
            return {"results": []}
            
        # Generate embedding (blocking, run in thread)
        query_embedding = await asyncio.to_thread(generate_query_embedding, query)
        if not query_embedding:
            raise HTTPException(status_code=500, detail="Failed to generate embedding for query")
            
        # Call RPC (blocking, run in thread)
        def run_rpc():
            return supabase_anon.rpc(
                "match_events",
                {
                    "query_embedding": query_embedding,
                    "match_threshold": 0.6,
                    "match_count": 50
                }
            ).execute()
            
        rpc_result = await asyncio.to_thread(run_rpc)
        
        matches = rpc_result.data
        if not matches:
            return {"results": []}
            
        # Fetch the CURRENT event rows for these IDs
        event_ids = [m["event_id"] for m in matches]
        
        # Fetch CURRENT event rows — explicit field list to exclude the embedding vector
        FIELDS = (
            "event_id, artist_id, artist_name, venue_id, venue_name, city, "
            "event_date, event_time, event_type, status, image_url, "
            "latitude, longitude, description, "
            "ticket_categories(price_inr)"
        )
        
        def fetch_events():
            return supabase_anon.table("events") \
                .select(FIELDS) \
                .in_("event_id", event_ids) \
                .execute()
                
        events_result = await asyncio.to_thread(fetch_events)
            
        current_events_list = check_and_update_event_status(events_result.data)
        current_events = {e["event_id"]: e for e in current_events_list}
        
        # Preserve similarity ranking from the RPC, filter active, limit to 20
        ranked_results = []
        for m in matches:
            event_id = m["event_id"]
            if event_id in current_events:
                event_data = current_events[event_id]
                # Filter out inactive events
                if event_data.get("status") in ("Completed", "Cancelled"):
                    continue
                event_data["similarity_score"] = m["similarity"]
                ranked_results.append(event_data)
                if len(ranked_results) >= 20:
                    break
                
        return {"results": ranked_results}
        
    except HTTPException:
        raise
    except asyncio.CancelledError:
        logger.info(f"Search request cancelled by client for query: {query}")
        return {"results": []}
    except Exception as e:
        logger.error(f"Search API error: {str(e)}", exc_info=True, extra={"query": query})
        raise HTTPException(status_code=500, detail="Internal server error during search")

class PlanRequest(BaseModel):
    message: str
    session_id: str

@router.post("/plan")
async def plan_my_night(payload: PlanRequest, current_user: dict = Depends(get_current_user)):
    """
    Endpoint for Plan My Night concierge agent.
    Integrated with the existing Customer AI Chat architecture.
    """
    from app.agents import customer_agent
    
    if current_user.get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="Admin accounts should use the Admin dashboard's agent chat instead.",
        )

    reply = await customer_agent.handle_website_message(
        user_id=current_user["user_id"],
        session_id=payload.session_id,
        message=payload.message,
    )
    return {"reply": reply}
