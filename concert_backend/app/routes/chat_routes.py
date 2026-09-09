from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from app.auth import get_current_user
from app.agents import customer_agent

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str  # identifies one conversation - keeps memory scoped per chat window


@router.post("")
async def chat(payload: ChatRequest, current_user: dict = Depends(get_current_user)):
    """
    Runs the customer assistant natively (no more forwarding to n8n) using
    the REAL user_id from the verified Supabase token, alongside the
    session_id used for persistent conversation memory (see
    app/agents/memory.py - backed by the chat_history table).
    """
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