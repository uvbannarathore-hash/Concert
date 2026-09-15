-- 21_pricing_notifications.sql
CREATE TABLE IF NOT EXISTS public.pricing_notifications (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  admin_user_id text NOT NULL,
  event_id text NOT NULL,
  category text NOT NULL,
  percent_full numeric NOT NULL,
  remaining_seats integer NOT NULL,
  days_remaining integer NOT NULL,
  velocity_seats integer NOT NULL,
  current_price numeric NOT NULL,
  suggested_price numeric NOT NULL,
  final_price numeric,
  justification text,
  status text NOT NULL DEFAULT 'pending'::text CHECK (status = ANY (ARRAY['pending'::text, 'approved'::text, 'dismissed'::text])),
  created_at timestamp with time zone DEFAULT now(),
  acted_at timestamp with time zone,
  CONSTRAINT pricing_notifications_pkey PRIMARY KEY (id),
  CONSTRAINT pricing_notifications_admin_user_id_fkey FOREIGN KEY (admin_user_id) REFERENCES public.users(user_id),
  CONSTRAINT pricing_notifications_event_id_fkey FOREIGN KEY (event_id) REFERENCES public.events(event_id)
);
