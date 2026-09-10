BEGIN;

-- 1. Fix the specific DY Patil Stadium event
UPDATE public.events 
SET city = 'Mumbai' 
WHERE event_id = 'EVT_SHAKIRA_MUMBAI' AND venue_name = 'DY Patil Stadium' AND city = 'DY Patil Stadium';

-- 2. Create venues table
CREATE TABLE public.venues (
    venue_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    city TEXT NOT NULL,
    address TEXT,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    capacity INTEGER,
    image_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(name, city)
);

-- Backup table (for safety)
CREATE TEMP TABLE temp_events_venue_backup AS 
SELECT event_id, venue_id, venue_name, city, latitude, longitude FROM public.events;

-- 3, 5, 6. Generate canonical venues
INSERT INTO public.venues (venue_id, name, city, latitude, longitude)
SELECT DISTINCT ON (LOWER(TRIM(venue_name)), LOWER(TRIM(city)))
    'VEN_' || UPPER(SUBSTRING(MD5(LOWER(TRIM(venue_name)) || LOWER(TRIM(city))) FROM 1 FOR 10)) AS new_venue_id,
    TRIM(venue_name) AS name,
    TRIM(city) AS city,
    latitude,
    longitude
FROM public.events
ORDER BY LOWER(TRIM(venue_name)), LOWER(TRIM(city)), 
    CASE WHEN latitude IS NOT NULL AND longitude IS NOT NULL THEN 0 ELSE 1 END;

-- 7. Update all events to point to the new canonical venue_id
UPDATE public.events e
SET venue_id = v.venue_id
FROM public.venues v
WHERE LOWER(TRIM(e.venue_name)) = LOWER(v.name) 
  AND LOWER(TRIM(e.city)) = LOWER(v.city);

-- 9. Verify orphaned events
DO $$
DECLARE
    orphaned_count INT;
BEGIN
    SELECT count(*)
    INTO orphaned_count
    FROM public.events e
    LEFT JOIN public.venues v ON e.venue_id = v.venue_id
    WHERE v.venue_id IS NULL;

    IF orphaned_count > 0 THEN
        RAISE EXCEPTION 'Migration verification failed: % events are orphaned. Aborting transaction.', orphaned_count;
    END IF;
END $$;

-- 8. Add constraint
ALTER TABLE public.events 
  ADD CONSTRAINT fk_events_venue 
  FOREIGN KEY (venue_id) 
  REFERENCES public.venues(venue_id);

COMMIT;
