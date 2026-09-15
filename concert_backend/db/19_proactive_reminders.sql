-- db/19_proactive_reminders.sql

-- 1. Add per-channel idempotency and concurrency lock
ALTER TABLE public.bookings ADD COLUMN IF NOT EXISTS reminder_email_sent BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.bookings ADD COLUMN IF NOT EXISTS reminder_telegram_sent BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.bookings ADD COLUMN IF NOT EXISTS reminder_claimed_at TIMESTAMPTZ;

-- 2. Safely decouple reminder updates from the generic webhook trigger.
-- We recreate the trigger to explicitly fire ONLY on meaningful state changes,
-- completely ignoring background changes to reminder flags.
DROP TRIGGER IF EXISTS booking_confirmed_notify ON public.bookings;

CREATE TRIGGER booking_confirmed_notify
AFTER UPDATE ON public.bookings
FOR EACH ROW
WHEN (
    OLD.status IS DISTINCT FROM NEW.status OR
    OLD.payment_status IS DISTINCT FROM NEW.payment_status OR
    OLD.refund_details IS DISTINCT FROM NEW.refund_details
)
EXECUTE FUNCTION notify_booking_confirmed();

-- Note: We intentionally DO NOT unschedule 'send-booking-reminders' cron yet,
-- as the Python replacement is local and requires a manual scheduler setup first.
