BEGIN;

-- 1. Fix confirmed bad data
UPDATE public.events 
SET city = 'Mumbai' 
WHERE event_id = 'EVT_SHAKIRA_MUMBAI'
  AND venue_name = 'DY Patil Stadium'
  AND city = 'DY Patil Stadium';


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
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);


-- 3. Normalized uniqueness
CREATE UNIQUE INDEX venues_name_city_normalized_idx
ON public.venues (LOWER(TRIM(name)), LOWER(TRIM(city)));


-- 4. Backup existing event venue relationships
CREATE TEMP TABLE temp_events_venue_backup AS
SELECT
    event_id,
    venue_id,
    venue_name,
    city,
    latitude,
    longitude
FROM public.events;


-- 5. Create canonical venues
INSERT INTO public.venues (
    venue_id,
    name,
    city,
    latitude,
    longitude
)
SELECT DISTINCT ON (
    LOWER(TRIM(venue_name)),
    LOWER(TRIM(city))
)
    'VEN_' ||
    UPPER(
        SUBSTRING(
            MD5(
                LOWER(TRIM(venue_name)) ||
                LOWER(TRIM(city))
            )
            FROM 1 FOR 10
        )
    ) AS new_venue_id,

    TRIM(venue_name) AS name,
    TRIM(city) AS city,
    latitude,
    longitude

FROM public.events

ORDER BY
    LOWER(TRIM(venue_name)),
    LOWER(TRIM(city)),
    CASE
        WHEN latitude IS NOT NULL
         AND longitude IS NOT NULL
        THEN 0
        ELSE 1
    END;


-- 6. Map events to canonical venues
--    AND clean venue_name/city
UPDATE public.events e
SET
    venue_id = v.venue_id,
    venue_name = v.name,
    city = v.city
FROM public.venues v
WHERE LOWER(TRIM(e.venue_name)) = LOWER(TRIM(v.name))
  AND LOWER(TRIM(e.city)) = LOWER(TRIM(v.city));


-- 7. Verify no orphaned events
DO $$
DECLARE
    orphaned_count INT;
BEGIN

    SELECT COUNT(*)
    INTO orphaned_count
    FROM public.events e
    LEFT JOIN public.venues v
        ON e.venue_id = v.venue_id
    WHERE v.venue_id IS NULL;

    IF orphaned_count > 0 THEN
        RAISE EXCEPTION
            'Migration verification failed: % events are orphaned. Aborting transaction.',
            orphaned_count;
    END IF;

END $$;


-- 8. Add FK
ALTER TABLE public.events
ADD CONSTRAINT fk_events_venue
FOREIGN KEY (venue_id)
REFERENCES public.venues(venue_id);


COMMIT;