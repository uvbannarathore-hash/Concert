from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from app.routes import artist_routes
from app.limiter import limiter
from app.routes import auth_routes, chat_routes, concert_routes, booking_routes, admin_routes, wishlist_routes, voice_routes, telegram_routes, show_routes, coupon_routes, venue_routes, review_routes
app = FastAPI(title="Concert Booking Assistant API")

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Turn Pydantic's raw validation errors into clean, user-friendly messages."""
    friendly_messages = []
    for error in exc.errors():
        loc = error.get("loc", [])
        field = loc[-1] if loc else "field"
        err_type = error.get("type", "")
        ctx = error.get("ctx", {})

        if err_type == "too_long" and field == "seat_ids":
            max_len = ctx.get("max_length", 20)
            friendly_messages.append(f"You can select a maximum of {max_len} seats per booking.")
        elif err_type == "too_short" and field == "seat_ids":
            friendly_messages.append("Please select at least one seat.")
        elif err_type in ("greater_than_equal", "less_than_equal") and field == "seats":
            ge = ctx.get("ge") or ctx.get("limit_value")
            le = ctx.get("le") or ctx.get("limit_value")
            if ge is not None:
                friendly_messages.append(f"You must book at least {ge} seat.")
            elif le is not None:
                friendly_messages.append(f"You can book a maximum of {le} seats at once.")
            else:
                friendly_messages.append(error.get("msg", "Invalid seats value."))
        else:
            friendly_messages.append(error.get("msg", "Invalid input."))

    detail = " ".join(friendly_messages) if friendly_messages else "Invalid request."
    return JSONResponse(status_code=422, content={"detail": detail})

# Allow the frontend (running on a different port/domain) to call this API.
# Tighten allow_origins to your actual frontend URL before going live.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://events-two-phi.vercel.app","http://localhost:5173",
        "http://127.0.0.1:5173","https://events-o0v9jffi9-yuvraj-e83c.vercel.app","https://concert-new-one.vercel.app",
],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_routes.router)
app.include_router(chat_routes.router)
app.include_router(concert_routes.router)
app.include_router(booking_routes.router)
app.include_router(admin_routes.router)
app.include_router(wishlist_routes.router)
app.include_router(voice_routes.router)
app.include_router(telegram_routes.router)
app.include_router(show_routes.router)
app.include_router(coupon_routes.router)
app.include_router(artist_routes.router)
app.include_router(venue_routes.router)
app.include_router(review_routes.router)


@app.get("/")
def health_check():
    return {"status": "ok", "message": "Concert Booking Assistant API is running"}