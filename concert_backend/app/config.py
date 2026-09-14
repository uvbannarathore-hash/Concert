import os
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

# Razorpay (Test/Sandbox first — swap key values in .env when going live,
# the code below never changes between test and live mode)
RAZORPAY_KEY_ID = os.getenv("RAZORPAY_KEY_ID", "rzp_test_dummy")
RAZORPAY_KEY_SECRET = os.getenv("RAZORPAY_KEY_SECRET", "dummy_secret")
RAZORPAY_WEBHOOK_SECRET = os.getenv("RAZORPAY_WEBHOOK_SECRET", "dummy_webhook_secret")

# LiveKit Cloud (website speech-to-speech voice assistant)
LIVEKIT_URL = os.getenv("LIVEKIT_URL", "wss://dummy.livekit.cloud")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY", "dummy_key")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET", "dummy_secret")

# Google Gemini (native Python admin + customer AI agents - replaces the
# old n8n "AI Agent" + "Google Gemini Chat Model" nodes)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "dummy_gemini_key")

# Telegram bot (customer assistant, Telegram channel - replaces n8n's
# "Telegram Trigger" + "Send a text message" nodes)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not SUPABASE_URL or not SUPABASE_ANON_KEY:
    raise RuntimeError(
        "SUPABASE_URL and SUPABASE_ANON_KEY must be set in your .env file"
    )

for key, val in [
    ("RAZORPAY_KEY_ID", RAZORPAY_KEY_ID),
    ("RAZORPAY_KEY_SECRET", RAZORPAY_KEY_SECRET),
    ("RAZORPAY_WEBHOOK_SECRET", RAZORPAY_WEBHOOK_SECRET),
    ("GEMINI_API_KEY", GEMINI_API_KEY),
]:
    if not val or val.startswith("dummy_"):
        print(f"[Warning] {key} is not configured in .env (using fallback dummy mode)")
