CREATE TABLE public.reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    event_id TEXT NOT NULL
        REFERENCES public.events(event_id) ON DELETE CASCADE,

    user_id TEXT NOT NULL
        REFERENCES public.users(user_id) ON DELETE CASCADE,

    rating INTEGER NOT NULL
        CHECK (rating BETWEEN 1 AND 5),

    review_text TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT unique_user_event_review
        UNIQUE (event_id, user_id)
);
