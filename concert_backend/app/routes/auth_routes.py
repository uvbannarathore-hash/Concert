from fastapi import APIRouter, Depends, HTTPException, Request
from app.limiter import limiter
from pydantic import BaseModel, EmailStr, Field
from app.supabase_client import supabase_anon, supabase_admin
from app.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None
    # phone, city, and address are now REQUIRED at signup time
    # (min_length=1 rejects empty strings, not just missing fields)
    phone: str = Field(..., pattern=r"^\+?[0-9\s\-]{7,15}$")
    city: str = Field(..., min_length=1)
    address: str = Field(..., min_length=1)


class UpdateProfileRequest(BaseModel):
    name: str | None = None
    phone: str | None = Field(default=None, pattern=r"^\+?[0-9\s\-]{7,15}$")
    city: str | None = None
    address: str | None = None
    payout_upi_id: str | None = None
    payout_bank_account: str | None = None
    payout_ifsc: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


@router.post("/signup")
@limiter.limit("5/minute")
def signup(request: Request, payload: SignupRequest):
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
    # explicitly upsert to make sure name/phone/city/address actually land
    # in that table too.
    try:
        supabase_admin.table("users").upsert(
            {
                "user_id": result.user.id,
                "email": result.user.email,
                "name": payload.name,
                "phone": payload.phone,
                "city": payload.city,
                "address": payload.address,
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
    Returns the logged-in user's profile info — used by the frontend for
    personalized greetings, the Edit Profile page, admin link visibility,
    and the organizer dashboard gate (is_organizer, plan_tier, payout fields).
    """
    result = (
        supabase_admin.table("users")
        .select(
            "name, phone, city, address, email, is_admin, "
            "is_organizer, plan_tier, plan_expiry_date, "
            "payout_upi_id, payout_bank_account, payout_ifsc, "
            "is_plus_member, plus_plan_type, plus_expiry_date"
        )
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
        "address": profile.get("address"),
        "is_admin": profile.get("is_admin", False),
        "is_organizer": profile.get("is_organizer", False),
        "plan_tier": profile.get("plan_tier", "starter"),
        "plan_expiry_date": profile.get("plan_expiry_date"),
        "payout_upi_id": profile.get("payout_upi_id"),
        "payout_bank_account": profile.get("payout_bank_account"),
        "payout_ifsc": profile.get("payout_ifsc"),
        "is_plus_member": bool(profile.get("is_plus_member")),
        "plus_plan_type": profile.get("plus_plan_type"),
        "plus_expiry_date": profile.get("plus_expiry_date"),
    }


@router.patch("/me")
def update_my_profile(payload: UpdateProfileRequest, current_user: dict = Depends(get_current_user)):
    """
    Lets a logged-in user update their own name/phone/city/address at any
    time (e.g. from an "Edit Profile" page), separate from signup.
    Only fields actually provided (non-None) are updated - others are
    left untouched.
    """
    updates = {k: v for k, v in payload.model_dump().items() if v is not None and v != ""}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update")

    supabase_admin.table("users").update(updates).eq("user_id", current_user["user_id"]).execute()
    return {"message": "Profile updated"}


@router.post("/login")
@limiter.limit("5/minute")
def login(request: Request, payload: LoginRequest):
    """
    Logs in an existing user and returns a Supabase access token.
    Implements Botnet brute-force protection (lockout).
    """
    client_ip = request.client.host if request.client else "unknown"
    
    from datetime import datetime, timedelta, timezone
    thirty_mins_ago = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()
    
    recent_fails = supabase_admin.table("failed_logins") \
        .select("ip_address") \
        .eq("email", payload.email) \
        .gte("attempt_time", thirty_mins_ago) \
        .execute()
        
    failed_ips = {row["ip_address"] for row in (recent_fails.data or [])}
    total_fails = len(recent_fails.data or [])
    
    if total_fails >= 5 and len(failed_ips) >= 2:
        # We use a generic message to prevent email enumeration
        raise HTTPException(status_code=401, detail="Invalid email or password")

    try:
        result = supabase_anon.auth.sign_in_with_password(
            {"email": payload.email, "password": payload.password}
        )
    except Exception:
        # 2. Log the failed attempt
        supabase_admin.table("failed_logins").insert({
            "email": payload.email,
            "ip_address": client_ip
        }).execute()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not result.session:
        # Log the failed attempt just in case
        supabase_admin.table("failed_logins").insert({
            "email": payload.email,
            "ip_address": client_ip
        }).execute()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # 3. Successful login - clear the failed attempts for this email
    # This prevents the user from accidentally locking themselves out later if they had some old failed attempts.
    supabase_admin.table("failed_logins").delete().eq("email", payload.email).execute()

    return {
        "access_token": result.session.access_token,
        "refresh_token": result.session.refresh_token,
        "user_id": result.user.id,
        "email": result.user.email,
    }