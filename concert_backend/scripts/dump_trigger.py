import asyncio
from dotenv import load_dotenv
import os
import httpx

load_dotenv()

from app.supabase_client import supabase_admin

async def main():
    try:
        res = supabase_admin.rpc("get_functiondef", {}).execute()
        print(res.data)
    except Exception as e:
        print(f"RPC failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
