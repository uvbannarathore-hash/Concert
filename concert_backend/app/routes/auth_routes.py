from fastapi import APIRouter, Depends,HTTPException
from pydantic import BaseModel, EmailStr
from app.supabase_client import supabase_anon, supabase_admin
from app.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None
    phone: str | None = None
    city: str | None = None


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    phone: str | None = None
    city: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/signup")
def signup(payload: SignupRequest):
    """
    Creates a new user via Supabase Auth.
    Supabase generates a unique user_id (UUID) for this user -
    this UUID is what we'll use everywhere instead of session_id.
    """
    try:
        result = supabase_anon.auth.sign_up(
            {
                "email": payload.email,
                "password": payload.password,
                "options": {"data": {"name": payload.name}},
            }
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not result.user:
        raise HTTPException(status_code=400, detail="Signup failed")

    # Supabase Auth only stores `name` inside the auth.users metadata blob -
    # it does NOT automatically copy it into our own public.users table.
    # A DB trigger (or similar) already creates the public.users row with
    # just the user_id/email when auth.users gets a new row, so here we
    # explicitly upsert to make sure `name` actually lands in that table too.
    try:
        supabase_admin.table("users").upsert(
            {
                "user_id": result.user.id,
                "email": result.user.email,
                "name": payload.name,
                "phone": payload.phone,
                "city": payload.city,
            }
        ).execute()
    except Exception as e:
        # Don't fail the whole signup if this secondary write has an issue -
        # the auth account still exists and can log in - but surface it in
        # server logs so it doesn't go unnoticed.
        print(f"[signup] Warning: failed to upsert profile into public.users: {e}")

    return {
        "message": "Signup successful. Please check your email to confirm your account (if email confirmation is enabled).",
        "user_id": result.user.id,
        "email": result.user.email,
    }


@router.get("/me")
def get_my_profile(current_user: dict = Depends(get_current_user)):
    """
    Returns the logged-in user's profile info (name, phone, city, email,
    is_admin) - used by the frontend for personalized greetings, the
    Edit Profile page, and to decide whether to show the Admin link.
    """
    result = (
        supabase_admin.table("users")
        .select("name, phone, city, email, is_admin")
        .eq("user_id", current_user["user_id"])
        .execute()
    )

    profile = result.data[0] if result.data else {}
    return {
        "user_id": current_user["user_id"],
        "email": profile.get("email", current_user["email"]),
        "name": profile.get("name"),
        "phone": profile.get("phone"),
        "city": profile.get("city"),
        "is_admin": profile.get("is_admin", False),
    }


@router.patch("/me")
def update_my_profile(payload: UpdateProfileRequest, current_user: dict = Depends(get_current_user)):
    """
    Lets a logged-in user update their own name/phone/city at any time
    (e.g. from an "Edit Profile" page), separate from signup.
    Only fields actually provided (non-None) are updated - others are
    left untouched.
    """
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    supabase_admin.table("users").update(updates).eq("user_id", current_user["user_id"]).execute()
    return {"message": "Profile updated"}


@router.post("/login")
def login(payload: LoginRequest):
    """
    Logs in an existing user and returns a Supabase access token.
    The frontend stores this token and sends it as:
        Authorization: Bearer <access_token>
    on every subsequent request.
    """
    try:
        result = supabase_anon.auth.sign_in_with_password(
            {"email": payload.email, "password": payload.password}
        )
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not result.session:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    return {
        "access_token": result.session.access_token,
        "refresh_token": result.session.refresh_token,
        "user_id": result.user.id,
        "email": result.user.email,
    }