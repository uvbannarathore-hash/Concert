import logging
from typing import Optional, Dict, Any
from google import genai
from google.genai import types
from app.config import GEMINI_API_KEY
from app.supabase_client import supabase_admin

logger = logging.getLogger("summarization_service")

# Initialize client using existing configuration
_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "models/gemini-3.1-flash-lite"

def get_review_summary(entity_type: str, entity_id: str) -> Dict[str, Any]:
    if entity_type not in ["event", "artist", "venue"]:
        return {"summary_text": None, "review_count": 0}

    valid_event_ids = [entity_id]
    if entity_type in ["artist", "venue"]:
        eq_field = "artist_id" if entity_type == "artist" else "venue_id"
        e_res = supabase_admin.table("events").select("event_id").eq(eq_field, entity_id).execute()
        valid_event_ids = [e["event_id"] for e in e_res.data] if e_res.data else []
        
    if not valid_event_ids:
        return {"summary_text": None, "review_count": 0}

    reviews_res = supabase_admin.table("reviews").select("review_text").in_("event_id", valid_event_ids).execute()
    reviews = reviews_res.data or []
    
    # Filter usable text reviews
    text_reviews = [r["review_text"].strip() for r in reviews if r.get("review_text") and r["review_text"].strip()]
    review_count = len(text_reviews)

    if review_count < 2:
        return {"summary_text": None, "review_count": review_count}

    # Check cache
    cache_res = supabase_admin.table("review_summaries").select("*").eq("entity_type", entity_type).eq("entity_id", entity_id).execute()
    cached = cache_res.data[0] if cache_res.data else None

    if cached and cached.get("review_count") == review_count and cached.get("summary_text"):
        return {"summary_text": cached["summary_text"], "review_count": review_count}

    # Cache miss or stale - call Gemini
    compiled_reviews = "\n".join(f"- {txt}" for txt in text_reviews)
    
    prompt = """Summarize ONLY the supplied reviews.
Do not invent facts.
Do not infer information that is not explicitly stated.
Do not fabricate complaints or praise.
Do not mention information outside the supplied reviews.
If reviewers disagree, reflect the disagreement.
Keep output to 1-2 concise sentences.
Do not use markdown.
Do not prepend "AI Summary:"."""

    try:
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Content(role="user", parts=[
                    types.Part.from_text(text=prompt),
                    types.Part.from_text(text=f"\n\nREVIEWS:\n{compiled_reviews}")
                ])
            ]
        )
        summary_text = response.text.strip()
        
        # Store in cache
        supabase_admin.table("review_summaries").upsert({
            "entity_type": entity_type,
            "entity_id": entity_id,
            "summary_text": summary_text,
            "review_count": review_count
        }, on_conflict="entity_type, entity_id").execute()
        
        return {"summary_text": summary_text, "review_count": review_count}
    except Exception as e:
        logger.error(f"Failed to generate AI summary: {e}")
        # Graceful degradation on Gemini failure
        return {"summary_text": None, "review_count": review_count}

def invalidate_summary_cache(event_id: str):
    """
    Invalidates the cache for the event and its associated artist/venue.
    """
    try:
        # Invalidate event
        supabase_admin.table("review_summaries").delete().eq("entity_type", "event").eq("entity_id", event_id).execute()
        
        # Fetch artist and venue
        e_res = supabase_admin.table("events").select("artist_id, venue_id").eq("event_id", event_id).execute()
        if e_res.data:
            event = e_res.data[0]
            if event.get("artist_id"):
                supabase_admin.table("review_summaries").delete().eq("entity_type", "artist").eq("entity_id", event["artist_id"]).execute()
            if event.get("venue_id"):
                supabase_admin.table("review_summaries").delete().eq("entity_type", "venue").eq("entity_id", event["venue_id"]).execute()
    except Exception as e:
        logger.error(f"Failed to invalidate cache: {e}")
