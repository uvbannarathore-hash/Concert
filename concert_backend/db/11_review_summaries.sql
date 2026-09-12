CREATE TABLE public.review_summaries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL
        CHECK (entity_type IN ('event', 'artist', 'venue')),
    entity_id TEXT NOT NULL,
    summary_text TEXT NOT NULL,
    review_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(entity_type, entity_id)
);
