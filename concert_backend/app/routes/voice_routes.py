import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from livekit import api

from app.auth import get_current_user
from app.config import LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET

router = APIRouter(prefix="/voice", tags=["voice"])


from pydantic import BaseModel
from app.supabase_client import supabase_admin

class TokenRequest(BaseModel):
    session_id: str

@router.post("/token")
def get_voice_token(payload: TokenRequest, current_user: dict = Depends(get_current_user)):
    """
    Issues a short-lived LiveKit access token for the logged-in user,
    tied to the provided chat session_id.
    """

    if current_user.get("is_admin"):
        raise HTTPException(
            status_code=403,
            detail="Admin accounts cannot use the booking voice assistant.",
        )

    if not (LIVEKIT_URL and LIVEKIT_API_KEY and LIVEKIT_API_SECRET):
        raise HTTPException(
            status_code=500,
            detail="Voice assistant is not configured (missing LiveKit credentials).",
        )

    # Security: validate session_id ownership
    session_id = payload.session_id
    history_check = (
        supabase_admin.table("chat_history")
        .select("user_id")
        .eq("session_id", session_id)
        .limit(1)
        .execute()
    )
    
    if history_check.data:
        if history_check.data[0]["user_id"] != current_user["user_id"]:
            raise HTTPException(
                status_code=403,
                detail="Session ID belongs to another user",
            )
    from livekit.protocol.agent_dispatch import CreateAgentDispatchRequest
    import asyncio
    
    room_name = f"voice-{session_id}"

    token = (
        api.AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(current_user["user_id"])
        .with_name(current_user.get("name") or "Guest")
        .with_ttl(timedelta(minutes=15))
        .with_grants(
            api.VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
            )
        )
    )

    # Explicitly dispatch the agent to this room to prevent implicit dev-mode
    # dispatch flakiness or capacity rejections.
    async def dispatch_agent():
        async with api.LiveKitAPI(LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET) as lkapi:
            try:
                await lkapi.agent_dispatch.create_dispatch(
                    CreateAgentDispatchRequest(
                        room=room_name,
                        agent_name="receptionist",
                    )
                )
            except Exception as e:
                # Log dispatch error but still return token so UI can connect
                # (it will be stuck on LISTENING..., but we shouldn't crash token minting)
                print(f"Failed to dispatch agent: {e}")

    try:
        asyncio.run(dispatch_agent())
    except Exception as e:
        print(f"Error running dispatch: {e}")

    return {
        "livekit_url": LIVEKIT_URL,
        "token": token.to_jwt(),
        "room_name": room_name,
    }