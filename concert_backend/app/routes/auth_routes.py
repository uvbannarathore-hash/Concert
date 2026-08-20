from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr
from app.supabase_client import supabase_anon

router = APIRouter(prefix="/auth", tags=["auth"])


class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None


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

    return {
        "message": "Signup successful. Please check your email to confirm your account (if email confirmation is enabled).",
        "user_id": result.user.id,
        "email": result.user.email,
    }


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
