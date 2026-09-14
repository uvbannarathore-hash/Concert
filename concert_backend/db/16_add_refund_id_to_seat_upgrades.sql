ALTER TABLE public.seat_upgrade_requests
ADD COLUMN IF NOT EXISTS refund_id TEXT;
