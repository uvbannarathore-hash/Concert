-- Enable the vector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Add the embedding column
ALTER TABLE public.events ADD COLUMN IF NOT EXISTS embedding vector(768);

-- Create HNSW index using cosine similarity
CREATE INDEX IF NOT EXISTS events_embedding_hnsw_idx 
    ON public.events 
    USING hnsw (embedding vector_cosine_ops);

-- Create RPC function for semantic search
CREATE OR REPLACE FUNCTION match_events(
    query_embedding vector(768),
    match_threshold float,
    match_count int
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
    ORDER BY e.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
