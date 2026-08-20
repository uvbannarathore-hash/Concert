from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.supabase_client import supabase_admin


# Tells FastAPI/Swagger that we use:
# Authorization: Bearer <access_token>
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    """
    Reads the Authorization: Bearer <token> header,
    verifies the token with Supabase, and returns
    the authenticated user's information.
    """

    token = credentials.credentials

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
        "user_id": user.id,
        "email": user.email,
    }