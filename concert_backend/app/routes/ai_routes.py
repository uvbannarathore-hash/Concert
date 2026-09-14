import logging
from fastapi import APIRouter, HTTPException, Body, Depends
from pydantic import BaseModel
from typing import List, Optional

from app.supabase_client import supabase_anon
from app.services.embedding_service import generate_query_embedding
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
def search_events(request: SearchRequest):
    query = request.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")
        
    if len(query) > 500:
        query = query[:500]
        
    try:
        # Generate embedding
        query_embedding = generate_query_embedding(query)
        if not query_embedding:
            raise HTTPException(status_code=500, detail="Failed to generate embedding for query")
            
        # Call RPC
        # Using a match_threshold of 0.6 (this can be tuned) and match_count of 20
        rpc_result = supabase_anon.rpc(
            "match_events",
            {
                "query_embedding": query_embedding,
                "match_threshold": 0.6,
                "match_count": 20
            }
        ).execute()
        
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
        events_result = supabase_anon.table("events") \
            .select(FIELDS) \
            .in_("event_id", event_ids) \
            .execute()
            
        current_events = {e["event_id"]: e for e in events_result.data}
        
        # Preserve similarity ranking from the RPC
        ranked_results = []
        for m in matches:
            event_id = m["event_id"]
            if event_id in current_events:
                event_data = current_events[event_id]
                event_data["similarity_score"] = m["similarity"]
                ranked_results.append(event_data)
                
        return {"results": ranked_results}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search API error: {str(e)}")
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
