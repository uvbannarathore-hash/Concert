CREATE TABLE public.waitlist (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    event_id TEXT NOT NULL
        REFERENCES public.events(event_id) ON DELETE CASCADE,

    user_id TEXT NOT NULL
        REFERENCES public.users(user_id) ON DELETE CASCADE,

    status TEXT NOT NULL DEFAULT 'Joined'
        CHECK (status IN ('Joined', 'Notified', 'Booked')),

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    CONSTRAINT unique_event_user_waitlist
        UNIQUE (event_id, user_id)
);
