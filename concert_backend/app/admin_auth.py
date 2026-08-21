from fastapi import Depends, HTTPException, status
from app.auth import get_current_user
from app.supabase_client import supabase_admin


async def get_current_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """
    Builds on get_current_user: first verifies the token (who is this?),
    then checks the is_admin flag in public.users (are they allowed here?).

    Attach this as a dependency to any admin-only route instead of
    get_current_user.
    """
    result = (
        supabase_admin.table("users")
        .select("is_admin")
        .eq("user_id", current_user["user_id"])
        .execute()
    )

    if not result.data or not result.data[0].get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )

    return current_user
