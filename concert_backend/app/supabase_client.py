from supabase import create_client, Client
import httpx
from functools import wraps
import logging

logger = logging.getLogger("supabase_client")

# WORKAROUND: Disable HTTP/2 globally for httpx
# Supabase-py hardcodes http2=True, which causes [WinError 10035] 
# on Windows due to stale connections in httpcore's HTTP/2 connection pool.
# We patch httpx to force HTTP/1.1 for all clients (including Supabase and Gemini).
_original_client_init = httpx.Client.__init__
_original_async_client_init = httpx.AsyncClient.__init__

@wraps(_original_client_init)
def _patched_client_init(self, *args, **kwargs):
    kwargs["http2"] = False
    _original_client_init(self, *args, **kwargs)

@wraps(_original_async_client_init)
def _patched_async_client_init(self, *args, **kwargs):
    kwargs["http2"] = False
    _original_async_client_init(self, *args, **kwargs)

httpx.Client.__init__ = _patched_client_init
httpx.AsyncClient.__init__ = _patched_async_client_init
logger.info("Patched httpx to disable HTTP/2 and prevent WinError 10035")

from app.config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY

# anon client -> used for signup/login (respects RLS, safe for public auth actions)
supabase_anon: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# service role client -> used for backend-only operations (bypasses RLS)
# NEVER expose the service role key to the frontend
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
