-- Migration 22: Group Booking Coordinator
-- Creates tables and indexes for the group booking feature.

CREATE TABLE public.group_booking_sessions (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    initiator_user_id text REFERENCES users(user_id) NOT NULL,
    event_id text REFERENCES events(event_id) NOT NULL,
    category text NOT NULL,
    total_seats integer NOT NULL,
    status text DEFAULT 'collecting_responses' 
        CHECK (status IN ('collecting_responses', 'ready', 'payment_pending', 'booked', 'expired', 'cancelled')),
    expires_at timestamptz NOT NULL,
    booking_id text REFERENCES bookings(booking_id),
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE TABLE public.group_booking_invites (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    group_session_id uuid REFERENCES group_booking_sessions(id) ON DELETE CASCADE,
    friend_email text NOT NULL,
    friend_name text,
    status text DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined')),
    responded_at timestamptz,
    created_at timestamptz DEFAULT now()
);

-- Indexes for performance and foreign keys
CREATE INDEX idx_group_sessions_initiator ON group_booking_sessions(initiator_user_id);
CREATE INDEX idx_group_sessions_status ON group_booking_sessions(status);
CREATE INDEX idx_group_sessions_expires ON group_booking_sessions(expires_at);
CREATE INDEX idx_group_sessions_booking_id ON group_booking_sessions(booking_id);
CREATE INDEX idx_group_invites_session ON group_booking_invites(group_session_id);
CREATE INDEX idx_group_invites_email ON group_booking_invites(friend_email);
