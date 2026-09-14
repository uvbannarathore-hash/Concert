BEGIN;

CREATE TABLE public.restaurants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    osm_id BIGINT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    cuisine TEXT,
    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    estimated_cost_for_two_inr INTEGER,
    source TEXT DEFAULT 'osm',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_restaurants_lat_lon ON public.restaurants (latitude, longitude);

COMMIT;
