-- db/18_update_stale_cancellation_threshold.sql

-- Allow the 15-minute abandoned checkout flow to run
-- before stale Pending bookings are cancelled.

CREATE OR REPLACE FUNCTION public.cancel_stale_pending_bookings()
RETURNS void
LANGUAGE plpgsql
AS $function$
BEGIN
    UPDATE public.bookings
    SET
        status = 'Cancelled',
        payment_status = 'Expired'
    WHERE status = 'Pending'
      AND payment_status = 'Pending'
      AND created_at < now() - interval '20 minutes';
END;
$function$;

-- Keep the existing stale-booking cron at every 5 minutes.
DO $$
BEGIN
    PERFORM cron.unschedule('cancel-stale-pending-bookings');
EXCEPTION
    WHEN OTHERS THEN
        NULL;
END $$;

SELECT cron.schedule(
    'cancel-stale-pending-bookings',
    '*/5 * * * *',
    'SELECT public.cancel_stale_pending_bookings();'
);