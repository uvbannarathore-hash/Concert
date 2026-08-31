import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Razorpay (Test/Sandbox first — swap key values in .env when going live,
# the code below never changes between test and live mode)
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET")

# LiveKit Cloud (website speech-to-speech voice assistant)
LIVEKIT_URL = os.getenv("LIVEKIT_URL")  # e.g. wss://your-project.livekit.cloud
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# Google Gemini (native Python admin + customer AI agents - replaces the
# old n8n "AI Agent" + "Google Gemini Chat Model" nodes)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Telegram bot (customer assistant, Telegram channel - replaces n8n's
# "Telegram Trigger" + "Send a text message" nodes)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_ANON_KEY must be set in your .env file"
    )