from supabase import create_client, Client
from app.config import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_SERVICE_ROLE_KEY

# anon client -> used for signup/login (respects RLS, safe for public auth actions)
supabase_anon: Client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

# service role client -> used for backend-only operations (bypasses RLS)
# NEVER expose the service role key to the frontend
supabase_admin: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
