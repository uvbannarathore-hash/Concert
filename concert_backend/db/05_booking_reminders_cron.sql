-- 05_booking_reminders_cron.sql

-- 1. Create the idempotent function to send booking reminders
CREATE OR REPLACE FUNCTION public.send_booking_reminders()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_updated_count integer;
    v_target_date date;
BEGIN
    -- Determine "tomorrow" in Asia/Kolkata time
    v_target_date := (CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date + 1;

    -- Atomically update eligible bookings and return the count
    WITH updated AS (
        UPDATE public.bookings b
        SET reminder_sent = true
        FROM public.events e
        WHERE b.event_id = e.event_id
          AND e.event_date::date = v_target_date
          AND b.status = 'Confirmed'
          -- Enforcing payment safety
          AND b.payment_status = 'Paid'
          -- Idempotency check ensures we don't re-trigger Webhooks
          AND b.reminder_sent = false
        RETURNING b.booking_id
    )
    SELECT count(*) INTO v_updated_count FROM updated;

    -- Log the execution
    RAISE LOG 'send_booking_reminders executed for date %: updated % bookings.', v_target_date, v_updated_count;

    RETURN v_updated_count;
END;
$$;

-- 2. Ensure the pg_cron extension is enabled
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- 3. Schedule the pg_cron job to run at 10:00 AM IST. 
-- Since PostgreSQL runs in UTC, 10:00 AM IST (UTC+5:30) is 4:30 AM UTC (30 4 * * *).
SELECT cron.schedule(
    'send-booking-reminders',
    '30 4 * * *',
    'SELECT public.send_booking_reminders();'
);
