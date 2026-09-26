-- Enable the vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add the embedding column
ALTER TABLE public.events ADD COLUMN IF NOT EXISTS embedding vector(768);

-- Create HNSW index using cosine similarity
CREATE INDEX IF NOT EXISTS events_embedding_hnsw_idx 
    ON public.events 
    USING hnsw (embedding vector_cosine_ops);

-- Create RPC function for semantic search.
-- start_date / end_date (ISO text, e.g. '2026-09-26') are optional.
-- When supplied they are applied as hard WHERE filters BEFORE the ORDER BY LIMIT,
-- ensuring the returned candidates all fall inside the requested window.
-- Passing NULL for either date disables that bound, so existing callers are unaffected.
CREATE OR REPLACE FUNCTION match_events(
    query_embedding vector(768),
    match_threshold float,
    match_count int,
    start_date text DEFAULT NULL,
    end_date text DEFAULT NULL
)
RETURNS TABLE (
    event_id text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        e.event_id,
        1 - (e.embedding <=> query_embedding) AS similarity
    FROM public.events e
    WHERE e.embedding IS NOT NULL
      AND 1 - (e.embedding <=> query_embedding) > match_threshold
      AND (start_date IS NULL OR e.event_date::text >= start_date)
      AND (end_date IS NULL OR e.event_date::text < end_date)
    ORDER BY e.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
