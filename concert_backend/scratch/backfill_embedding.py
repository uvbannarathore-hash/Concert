from app.supabase_client import supabase_admin
from app.services import embedding_service

EVENT_ID = 'EVT8dda4348a603'

# Fetch the event row to build the embedding payload
row = supabase_admin.table('events').select(
    'event_id, artist_name, venue_name, city, event_date, event_time, event_type, description'
).eq('event_id', EVENT_ID).execute().data[0]
print(f"Event row: {row}")

# Check embedding before
emb_before = supabase_admin.table('events').select('embedding').eq('event_id', EVENT_ID).execute().data[0]
is_null_before = emb_before['embedding'] is None
print(f"embedding before: {'NULL' if is_null_before else 'already populated'}")

# Generate
vector = embedding_service.generate_event_embedding(row)
if not vector:
    print('ERROR: generate_event_embedding returned None')
else:
    print(f'Generated vector length: {len(vector)}')
    supabase_admin.table('events').update({'embedding': vector}).eq('event_id', EVENT_ID).execute()
    print('Stored embedding.')

# Confirm after
emb_after = supabase_admin.table('events').select('embedding').eq('event_id', EVENT_ID).execute().data[0]
is_null_after = emb_after['embedding'] is None
if is_null_after:
    print('FAIL: embedding is still NULL after write')
else:
    print(f'CONFIRMED: embedding is now populated (vector length {len(emb_after["embedding"])})')
