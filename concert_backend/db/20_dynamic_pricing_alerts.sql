-- db/20_dynamic_pricing_alerts.sql

ALTER TABLE public.ticket_categories
ADD COLUMN IF NOT EXISTS last_pricing_alert_at TIMESTAMPTZ;
