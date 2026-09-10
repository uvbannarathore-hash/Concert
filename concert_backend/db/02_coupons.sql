-- 1. Create coupons table
CREATE TABLE public.coupons (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  code text NOT NULL UNIQUE,
  discount_type text NOT NULL CHECK (discount_type IN ('fixed', 'percentage')),
  discount_value numeric NOT NULL CHECK (discount_value > 0),
  max_uses integer NOT NULL CHECK (max_uses > 0),
  current_uses integer NOT NULL DEFAULT 0,
  max_uses_per_user integer NOT NULL DEFAULT 1 CHECK (max_uses_per_user > 0),
  valid_from timestamp with time zone,
  valid_until timestamp with time zone,
  event_id text REFERENCES public.events(event_id),
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamp with time zone DEFAULT now()
);

-- 2. Create coupon_usage tracking table
CREATE TABLE public.coupon_usage (
  id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  coupon_id uuid NOT NULL REFERENCES public.coupons(id),
  user_id text NOT NULL REFERENCES public.users(user_id),
  booking_id text NOT NULL REFERENCES public.bookings(booking_id),
  used_at timestamp with time zone DEFAULT now(),
  CONSTRAINT unique_coupon_booking UNIQUE(coupon_id, booking_id)
);

-- 3. Modify bookings table
ALTER TABLE public.bookings
  ADD COLUMN coupon_id uuid REFERENCES public.coupons(id),
  ADD COLUMN discount_amount numeric NOT NULL DEFAULT 0,
  ADD COLUMN total_amount numeric;

-- 4. Create the consume_coupon atomic RPC
CREATE OR REPLACE FUNCTION public.consume_coupon(
  p_booking_id text,
  p_user_id text,
  p_coupon_id uuid
) RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_current_uses int;
  v_max_uses int;
  v_max_uses_per_user int;
  v_user_uses int;
BEGIN
  -- Lock the coupon row for update
  SELECT current_uses, max_uses, max_uses_per_user 
  INTO v_current_uses, v_max_uses, v_max_uses_per_user
  FROM public.coupons 
  WHERE id = p_coupon_id 
  FOR UPDATE;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'Coupon not found';
  END IF;

  -- Check global limits
  IF v_current_uses >= v_max_uses THEN
    RAISE EXCEPTION 'Coupon usage limit reached';
  END IF;

  -- Check per-user limits
  SELECT count(*) INTO v_user_uses 
  FROM public.coupon_usage 
  WHERE coupon_id = p_coupon_id AND user_id = p_user_id;

  IF v_user_uses >= v_max_uses_per_user THEN
    RAISE EXCEPTION 'Per-user coupon limit reached';
  END IF;

  -- Increment global usage
  UPDATE public.coupons 
  SET current_uses = current_uses + 1 
  WHERE id = p_coupon_id;

  -- Insert usage record
  INSERT INTO public.coupon_usage (coupon_id, user_id, booking_id)
  VALUES (p_coupon_id, p_user_id, p_booking_id);

END;
$$;
