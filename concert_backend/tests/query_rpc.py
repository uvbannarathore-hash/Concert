import psycopg2
try:
    conn = psycopg2.connect("postgresql://postgres.npxcswvckvwvjcyeblrt:LivewireSupabase2026%24%24@aws-0-ap-south-1.pooler.supabase.com:6543/postgres")
    cur = conn.cursor()
    cur.execute("SELECT proname, pg_get_functiondef(oid) FROM pg_proc WHERE proname = 'create_event_with_pricing';")
    row = cur.fetchone()
    if row:
        print(row[1])
    else:
        print("RPC not found")
    conn.close()
except Exception as e:
    print("Error:", e)
