import logging
from typing import Optional, List
from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY

logger = logging.getLogger("embedding_service")

# Initialize client using existing configuration
_client = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "models/gemini-embedding-2"
EMBEDDING_DIMENSION = 768

def _generate_embedding(text: str, task_type: str) -> Optional[List[float]]:
    try:
        if not text or not text.strip():
            return None
            
        response = _client.models.embed_content(
            model=MODEL_NAME,
            contents=text.strip(),
            config=types.EmbedContentConfig(
                output_dimensionality=EMBEDDING_DIMENSION,
                task_type=task_type
            )
        )
        
        # Verify dimension
        if response.embeddings and len(response.embeddings) > 0:
            embedding = response.embeddings[0].values
            if len(embedding) == EMBEDDING_DIMENSION:
                return embedding
            else:
                logger.error(f"Embedding dimension mismatch: expected {EMBEDDING_DIMENSION}, got {len(embedding)}")
                return None
        return None
    except Exception as e:
        logger.error(f"Failed to generate embedding: {str(e)}")
        return None

def generate_event_embedding(event: dict) -> Optional[List[float]]:
    """
    Generate embedding for an event document.
    Format: title: {artist_name} | text: {event content}
    """
    artist_name = event.get("artist_name", "") or ""
    venue_name = event.get("venue_name", "") or ""
    city = event.get("city", "") or ""
    event_type = event.get("event_type", "") or ""
    description = event.get("description", "") or ""
    event_date = event.get("event_date", "") or ""
    event_time = event.get("event_time", "") or ""
    
    content_parts = []
    if venue_name: content_parts.append(f"Venue: {venue_name}")
    if city: content_parts.append(f"City: {city}")
    if event_type: content_parts.append(f"Type: {event_type}")
    if event_date or event_time: content_parts.append(f"Date/Time: {event_date} {event_time}")
    if description: content_parts.append(f"Description: {description}")
    
    content_text = " - ".join(content_parts)
    full_text = f"title: {artist_name} | text: {content_text}"
    
    return _generate_embedding(full_text, task_type="RETRIEVAL_DOCUMENT")

def generate_query_embedding(query: str) -> Optional[List[float]]:
    """
    Generate embedding for a search query.
    Format: task: search result | query: {user query}
    """
    full_text = f"task: search result | query: {query}"
    return _generate_embedding(full_text, task_type="RETRIEVAL_QUERY")
