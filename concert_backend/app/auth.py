from fastapi import Header, HTTPException, status
from app.supabase_client import supabase_admin


async def get_current_user(authorization: str = Header(...)) -> dict:
    """
    Reads the 'Authorization: Bearer <token>' header, verifies it with
    Supabase, and returns the authenticated user's info.

    This is where the REAL user_id comes from - no more session_id
    workarounds. Attach this as a dependency to any route that needs
    to know who the logged-in user is.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization header",
        )

    token = authorization.replace("Bearer ", "").strip()

    try:
        user_response = supabase_admin.auth.get_user(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    if not user_response or not user_response.user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )

    user = user_response.user
    return {
        "user_id": user.id,          # <-- this is the real user_id (UUID)
        "email": user.email,
    }
