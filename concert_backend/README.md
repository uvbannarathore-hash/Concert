# Concert Booking Assistant - Backend (FastAPI)

## Setup

1. Create a virtual environment and install dependencies:
   ```
   python -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your real values:
   ```
   cp .env.example .env
   ```
   - `SUPABASE_URL` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY`
     → Supabase Dashboard → Project Settings → API
   - `N8N_WEBHOOK_URL`
     → Your n8n workflow's **production** Webhook URL (after clicking Publish/Active,
       not the "webhook-test" URL used while building)

3. Run the server:
   ```
   uvicorn app.main:app --reload
   ```

4. Open the interactive API docs:
   ```
   http://127.0.0.1:8000/docs
   ```

## Endpoints

| Method | Path                       | Auth required | Purpose |
|--------|----------------------------|----------------|---------|
| POST   | /auth/signup               | No             | Create a new user |
| POST   | /auth/login                | No             | Log in, get access_token |
| POST   | /chat                      | Yes            | Send a message to the AI Agent (via n8n) |
| GET    | /concerts                  | No             | List all events (optional ?city=) |
| GET    | /concerts/{event_id}       | No             | Event detail + ticket categories |
| POST   | /bookings                  | Yes            | Create a booking |
| GET    | /bookings/me                | Yes            | List my bookings |
| POST   | /bookings/{booking_id}/cancel | Yes         | Cancel a booking |

## How auth works

1. Frontend calls `/auth/signup` or `/auth/login`.
2. Backend talks to Supabase Auth, gets back an `access_token` and the user's
   real `user_id` (a UUID Supabase generates).
3. Frontend stores the `access_token` and sends it on every request as:
   ```
   Authorization: Bearer <access_token>
   ```
4. Backend verifies this token on protected routes (`/chat`, `/bookings/*`)
   and extracts the real `user_id` from it - no more `session_id`-as-`user_id`
   workaround.

## Quick test with curl

```bash
# Signup
curl -X POST http://127.0.0.1:8000/auth/signup \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test1234","name":"Test User"}'

# Login
curl -X POST http://127.0.0.1:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"test@example.com","password":"test1234"}'
# -> copy the access_token from the response

# Chat (replace TOKEN)
curl -X POST http://127.0.0.1:8000/chat \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer TOKEN" \
  -d '{"message":"Show me my previous bookings","session_id":"abc123"}'
```
