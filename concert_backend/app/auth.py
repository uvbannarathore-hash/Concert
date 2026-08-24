from fastapi import Header, HTTPException, status
from app.supabase_client import supabase_admin


async def get_current_user(authorization: str = Header(...)) -> dict:
    """
    Reads the 'Authorization: Bearer <token>' header, verifies it with
    Supabase, and fetches user profile details (including is_admin) from the users table.
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
    user_id = str(user.id)

    # Database se user ka role / is_admin fetch karo
    is_admin = False
    name = ""
    try:
        profile_res = (
            supabase_admin.table("users")
            .select("is_admin, name")
            .eq("user_id", user_id)
            .execute()
        )
        if profile_res.data and len(profile_res.data) > 0:
            user_data = profile_res.data[0]
            is_admin = bool(user_data.get("is_admin", False))
            name = user_data.get("name", "")
    except Exception:
        pass

    return {
        "user_id": user_id,
        "email": user.email,
        "name": name,
        "is_admin": is_admin,
    }