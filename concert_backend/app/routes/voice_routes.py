import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from livekit import api

from app.auth import get_current_user
from app.config import LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET

router = APIRouter(prefix="/voice", tags=["voice"])


@router.post("/token")
def get_voice_token(current_user: dict = Depends(get_current_user)):
    """
    Issues a short-lived LiveKit access token for the logged-in user.
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

    room_name = f"voice-{current_user['user_id']}-{uuid.uuid4().hex[:8]}"

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

    return {
        "livekit_url": LIVEKIT_URL,
        "token": token.to_jwt(),
        "room_name": room_name,
    }