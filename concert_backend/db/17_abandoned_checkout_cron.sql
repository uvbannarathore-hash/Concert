-- db/17_abandoned_checkout_cron.sql

ALTER TABLE public.bookings ADD COLUMN IF NOT EXISTS abandoned_email_sent BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.bookings ADD COLUMN IF NOT EXISTS abandoned_telegram_sent BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE public.bookings ADD COLUMN IF NOT EXISTS last_abandoned_trigger_at TIMESTAMPTZ;

CREATE OR REPLACE FUNCTION public.trigger_abandoned_checkouts()
RETURNS integer
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_updated_count integer := 0;
    v_booking_id text;
    v_url text := 'https://yacolxewrrlsxsbblulr.supabase.co/functions/v1/send-booking-notifications';
    v_secret text;
BEGIN
    -- Securely retrieve the existing webhook secret from Supabase Vault
    SELECT decrypted_secret INTO v_secret 
    FROM vault.decrypted_secrets 
    WHERE name = 'DB_WEBHOOK_SHARED_SECRET' 
    LIMIT 1;
    
    IF v_secret IS NULL THEN
        RAISE EXCEPTION 'Webhook secret not found in vault.decrypted_secrets (name=DB_WEBHOOK_SHARED_SECRET)';
    END IF;

    FOR v_booking_id IN (
        WITH updated AS (
            UPDATE public.bookings
            SET last_abandoned_trigger_at = now()
            WHERE status = 'Pending'
              AND payment_status = 'Pending'
              AND created_at <= now() - interval '15 minutes'
              AND (abandoned_email_sent = false OR abandoned_telegram_sent = false)
            RETURNING booking_id
        )
        SELECT booking_id FROM updated
    ) LOOP
        -- Invoke the Edge Function using an explicit scheduler payload
        PERFORM net.http_post(
            url := v_url,
            headers := jsonb_build_object(
                'Content-Type', 'application/json',
                'x-webhook-secret', v_secret
            ),
            body := jsonb_build_object(
                'type', 'abandoned_checkout',
                'booking_id', v_booking_id
            )
        );
        
        v_updated_count := v_updated_count + 1;
    END LOOP;

    IF v_updated_count > 0 THEN
        RAISE LOG 'trigger_abandoned_checkouts executed: sent pg_net invocation for % bookings.', v_updated_count;
    END IF;

    RETURN v_updated_count;
END;
$$;

DO $$
BEGIN
    PERFORM cron.unschedule('trigger-abandoned-checkouts');
EXCEPTION WHEN OTHERS THEN
END $$;

SELECT cron.schedule(
    'trigger-abandoned-checkouts',
    '* * * * *',
    'SELECT public.trigger_abandoned_checkouts();'
);
