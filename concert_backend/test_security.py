import asyncio
from app.supabase_client import supabase_admin
from app.agents import customer_agent

async def main():
    # Find two real users
    users = supabase_admin.table("users").select("user_id, name").limit(2).execute()
    if len(users.data) < 2:
        print("Not enough users to test cross-user security.")
        return
    
    u1, u2 = users.data[0], users.data[1]
    u1_id, u1_name = u1['user_id'], u1.get('name', 'User1')
    u2_id, u2_name = u2['user_id'], u2.get('name', 'User2')
    
    print(f"Testing with User A: {u1_name} ({u1_id})")
    print(f"Testing with User B: {u2_name} ({u2_id})")
    
    handlers_u1 = customer_agent._build_bound_handlers(u1_id, chat_id=None)
    handlers_u2 = customer_agent._build_bound_handlers(u2_id, chat_id=None)
    
    print(f"\nCalling get_user_hosted_shows for User A...")
    res_u1 = handlers_u1["get_user_hosted_shows"]()
    print(res_u1)
    
    print(f"\nCalling get_user_hosted_shows for User B...")
    res_u2 = handlers_u2["get_user_hosted_shows"]()
    print(res_u2)

if __name__ == "__main__":
    asyncio.run(main())
