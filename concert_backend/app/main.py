from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth_routes, chat_routes, concert_routes, booking_routes, admin_routes, wishlist_routes

app = FastAPI(title="Concert Booking Assistant API")

# Allow the frontend (running on a different port/domain) to call this API.
# Tighten allow_origins to your actual frontend URL before going live.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.get("/")
def health_check():
    return {"status": "ok", "message": "Concert Booking Assistant API is running"}
