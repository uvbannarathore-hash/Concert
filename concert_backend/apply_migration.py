import os
import psycopg2
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

db_url = os.environ.get("DIRECT_URL") or os.environ.get("DATABASE_URL")
if db_url and db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://")

print(f"Connecting to {db_url.split('@')[-1] if db_url else None}")

with open("db/17_abandoned_checkout_cron.sql", "r") as f:
    sql = f.read()

conn = psycopg2.connect(db_url)
conn.autocommit = True
with conn.cursor() as cur:
    cur.execute(sql)
    print("Migration executed successfully!")
conn.close()
