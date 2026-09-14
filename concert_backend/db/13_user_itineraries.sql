CREATE TABLE IF NOT EXISTS user_itineraries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    event_id TEXT NOT NULL,
    plan_json JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Enable RLS
ALTER TABLE user_itineraries ENABLE ROW LEVEL SECURITY;

-- Allow users to view their own itineraries
CREATE POLICY "Users can view their own itineraries"
    ON user_itineraries
    FOR SELECT
    USING (auth.uid()::text = user_id);

-- Allow users to insert their own itineraries
CREATE POLICY "Users can insert their own itineraries"
    ON user_itineraries
    FOR INSERT
    WITH CHECK (auth.uid()::text = user_id);

-- Allow service role full access
CREATE POLICY "Service role has full access to user_itineraries"
    ON user_itineraries
    USING (auth.jwt() ->> 'role' = 'service_role');
