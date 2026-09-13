-- Add refund_details column to bookings table to pass refund breakdown to Edge Function
ALTER TABLE public.bookings ADD COLUMN IF NOT EXISTS refund_details JSONB;
