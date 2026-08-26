import os
from dotenv import load_dotenv

load_dotenv()

# LiveKit connection (only needed if you also want to run the LiveKit-based
# agent.py path via SIP trunk — NOT required for tata_voice_server.py,
# which talks to Tata Smartflo directly over its own WebSocket)
LIVEKIT_URL = os.getenv("LIVEKIT_URL")
LIVEKIT_API_KEY = os.getenv("LIVEKIT_API_KEY")
LIVEKIT_API_SECRET = os.getenv("LIVEKIT_API_SECRET")

# API Keys
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
CARTESIA_VOICE_ID = os.getenv("CARTESIA_VOICE_ID", "c6bbc7d5-4b35-4d49-b1c6-4417019a61c1")

# Local LLM Fallback (optional)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/v1")

# NOTE: no DATABASE_URL here — voice_db.py talks to Supabase via the
# existing app.supabase_client (service-role), reusing SUPABASE_URL /
# SUPABASE_SERVICE_ROLE_KEY already defined in app/config.py, so those
# don't need to be duplicated in this file.

# Platform Identity
PLATFORM_NAME = os.getenv("VOICE_PLATFORM_NAME", "Concert")
AGENT_NAME = os.getenv("VOICE_AGENT_NAME", "Maya")
