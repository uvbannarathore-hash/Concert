from fastapi import Depends, HTTPException, status
from app.auth import get_current_user
from app.supabase_client import supabase_admin


async def get_current_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Builds on get_current_user: first verifies the token (who is this?),
    then checks the is_admin flag.

    Attach this as a dependency to any admin-only route instead of
    get_current_user.
    """
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user
