import requests, os
from dotenv import load_dotenv
load_dotenv('.env')

url = f"{os.environ['SUPABASE_URL']}/rest/v1/rpc/exec_sql"
headers = {
    'apikey': os.environ['SUPABASE_SERVICE_ROLE_KEY'],
    'Authorization': f"Bearer {os.environ['SUPABASE_SERVICE_ROLE_KEY']}",
    'Content-Type': 'application/json'
}

# First let's just see if exec_sql exists
res = requests.post(url, headers=headers, json={"query": "SELECT 1;"})
print("exec_sql res:", res.status_code, res.text)
