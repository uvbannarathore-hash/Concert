from app.supabase_client import supabase_admin
import json

plan = {
    "grand_total_inr": 4107, 
    "restaurant_options": [{"name": "Origami Japanese & Korean Restaurant", "cuisine": "Asian", "estimated_cost_for_two_inr": 2000, "google_maps_url": "https://www.google.com/maps/dir/?api=1&destination=19.0760,72.8777"}], 
    "travel_directions": {"estimated_time_mins": 5, "distance_km": 2.1, "estimated_cab_fare_inr": 107, "uber_deep_link": "https://m.uber.com/ul/?action=setPickup&dropoff[latitude]=19.0760&dropoff[longitude]=72.8777"}
}

supabase_admin.table('user_itineraries').update({'plan_json': plan}).eq('id', '7b79763e-587e-47cb-8b86-cb1cba4484bb').execute()
print("Updated successfully.")
