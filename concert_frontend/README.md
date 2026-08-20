# LIVEWIRE — Concert Booking Frontend

React + Vite + Tailwind frontend for the concert booking assistant.
Talks to the FastAPI backend from Part 5 at `http://127.0.0.1:8000`.

## Setup

```bash
npm install
npm run dev
```

Open `http://localhost:5173`.

**Make sure the FastAPI backend is already running** (`uvicorn app.main:app --reload`)
before using this — every page except the auth form calls it.

## Pages

| Route | What it does |
|---|---|
| `/` | Browse concerts, filter by city |
| `/concerts/:eventId` | Concert detail, pick a ticket category, book |
| `/login` | Signup / login (talks to `/auth/signup`, `/auth/login`) |
| `/bookings` | View + cancel your bookings (requires login) |
| `/chat` | Talk to the AI booking assistant (requires login) |

## How auth flows through

1. `AuthPage` calls `api.login()`, which stores the Supabase `access_token`
   in `localStorage`.
2. `lib/api.js` attaches `Authorization: Bearer <token>` automatically on
   every request that needs it (`/chat`, `/bookings/*`).
3. A fresh `session_id` (random UUID) is generated per login and stored in
   `sessionStorage` — used only for short-term chat memory continuity, never
   for identifying the user.

## Before deploying

- Change `BASE_URL` in `src/lib/api.js` from `http://127.0.0.1:8000` to your
  deployed backend URL.
- In the backend's `app/main.py`, replace `allow_origins=["*"]` with your
  actual frontend domain.
