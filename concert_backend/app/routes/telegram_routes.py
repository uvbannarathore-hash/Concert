"""
telegram_routes.py — Webhook endpoint for the Telegram bot, replacing
n8n's "Telegram Trigger" + "Send a text message" nodes.

Setup (one-time, outside this codebase):
1. Get a bot token from @BotFather on Telegram if you don't already have
   one, and set TELEGRAM_BOT_TOKEN in your backend's .env.
2. Register this endpoint as your bot's webhook by visiting (once, after
   deploying, replacing the placeholders):
   https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=<your-backend-domain>/telegram/webhook
   You should get back {"ok":true,"result":true,...}. Telegram requires
   the URL to be HTTPS and publicly reachable - this won't work against
   localhost, only your deployed backend.
3. To verify it's registered: visit
   https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getWebhookInfo
"""

import httpx
from fastapi import APIRouter, Request
from app.config import TELEGRAM_BOT_TOKEN
from app.agents import customer_tools

router = APIRouter(prefix="/telegram", tags=["telegram"])

TELEGRAM_API_BASE = "https://api.telegram.org"


async def _send_message(chat_id, text: str) -> None:
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"{TELEGRAM_API_BASE}/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    async with httpx.AsyncClient(timeout=15.0) as client:
        await client.post(url, json={"chat_id": chat_id, "text": text})


@router.post("/webhook")
async def telegram_webhook(request: Request):
    """
    Telegram calls this for every incoming message once the webhook is
    registered (see module docstring). We always return 200 immediately
    after handling (or intentionally ignoring) the update, since Telegram
    retries deliveries that don't get a fast 2xx response.
    """
    update = await request.json()
    message = update.get("message")

    if not message or "text" not in message:
        # Ignore non-text updates (photos, stickers, edited messages, etc.)
        # for now - same scope as the n8n version, which only handled text.
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message["text"]
    from_user = message.get("from", {})
    telegram_name = " ".join(filter(None, [from_user.get("first_name"), from_user.get("last_name")])) or None

    try:
        reply = await customer_tools.handle_telegram_message(
            chat_id=str(chat_id),
            telegram_name=telegram_name,
            message=text,
        )
    except Exception as e:
        reply = f"Sorry, something went wrong on my end: {e}"

    await _send_message(chat_id, reply)
    return {"ok": True}