from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth_routes, chat_routes, concert_routes, booking_routes, admin_routes, wishlist_routes, voice_routes, telegram_routes, show_routes

app = FastAPI(title="Concert Booking Assistant API")

# Allow the frontend (running on a different port/domain) to call this API.
# Tighten allow_origins to your actual frontend URL before going live.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://events-two-phi.vercel.app","http://localhost:5173",
        "http://127.0.0.1:5173","https://events-o0v9jffi9-yuvraj-e83c.vercel.app","https://concert-new-one.vercel.app",
],  
    allow_origin_regex=r"https?://.*",
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


@app.get("/")
def health_check():
    return {"status": "ok", "message": "Concert Booking Assistant API is running"}