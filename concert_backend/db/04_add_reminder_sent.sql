-- Add reminder_sent flag to bookings for idempotent email reminders
ALTER TABLE public.bookings ADD COLUMN reminder_sent BOOLEAN DEFAULT false;
