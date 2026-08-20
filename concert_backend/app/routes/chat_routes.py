import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth import get_current_user
from app.config import N8N_WEBHOOK_URL

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str  # still useful for short-term memory / conversation continuity


@router.post("")
async def chat(payload: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    Forwards the user's message to the n8n AI Agent webhook, attaching
    the REAL user_id (from the verified Supabase token) alongside the
    session_id (used only for short-term conversation memory).
    """
    body = {
        "user_id": current_user["user_id"],
        "session_id": payload.session_id,
        "message": payload.message,
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(N8N_WEBHOOK_URL, json=body)
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Failed to reach AI assistant: {e}")

    return response.json()
