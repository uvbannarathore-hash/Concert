"""
telegram_routes.py — Webhook endpoint for the Telegram bot, replacing
n8n's "Telegram Trigger" + "Send a text message" nodes.
...
"""

import httpx
from fastapi import APIRouter, Request
from app.config import TELEGRAM_BOT_TOKEN
from app.agents import customer_agent

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
    update = await request.json()
    message = update.get("message")

    if not message or "text" not in message:
        return {"ok": True}

    chat_id = message["chat"]["id"]
    text = message["text"]
    from_user = message.get("from", {})
    telegram_name = " ".join(filter(None, [from_user.get("first_name"), from_user.get("last_name")])) or None

    try:
        reply = await customer_agent.handle_telegram_message(
            chat_id=str(chat_id),
            telegram_name=telegram_name,
            message=text,
        )
    except Exception as e:
        reply = f"Sorry, something went wrong on my end: {e}"

    await _send_message(chat_id, reply)
    return {"ok": True}