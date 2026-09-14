-- Table Definition
CREATE TABLE IF NOT EXISTS public.seat_upgrade_requests (
    id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id text NOT NULL REFERENCES public.users(user_id) ON DELETE CASCADE,
    event_id text NOT NULL REFERENCES public.events(event_id) ON DELETE CASCADE,
    original_booking_id text NOT NULL REFERENCES public.bookings(booking_id) ON DELETE CASCADE,
    current_category text NOT NULL,
    desired_category text NOT NULL,
    status text NOT NULL CHECK (status IN ('active', 'notified', 'processing', 'payment_pending', 'refund_pending', 'upgraded', 'cancelled')),
    created_at timestamp with time zone DEFAULT now(),
    updated_at timestamp with time zone DEFAULT now()
);

-- Unique constraint: A user can only have one active/pending upgrade request per booking
CREATE UNIQUE INDEX IF NOT EXISTS idx_seat_upgrade_requests_unique_active 
ON public.seat_upgrade_requests(original_booking_id) 
WHERE status IN ('active', 'notified', 'processing', 'payment_pending', 'refund_pending');

-- Updated At Trigger
CREATE OR REPLACE FUNCTION update_seat_upgrades_updated_at_column()
RETURNS TRIGGER AS 
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
 language 'plpgsql';

DROP TRIGGER IF EXISTS trg_seat_upgrades_updated_at ON public.seat_upgrade_requests;
CREATE TRIGGER trg_seat_upgrades_updated_at
BEFORE UPDATE ON public.seat_upgrade_requests
FOR EACH ROW EXECUTE FUNCTION update_seat_upgrades_updated_at_column();


-- Cron function to check for available upgrades
CREATE OR REPLACE FUNCTION public.check_seat_upgrades()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS 
DECLARE
    v_req record;
    v_available_seats integer;
    v_booking_status text;
    v_is_seat_map boolean;
BEGIN
    -- Iterate over active requests safely
    FOR v_req IN
        SELECT r.id, r.event_id, r.desired_category, r.original_booking_id, b.seats_booked
        FROM public.seat_upgrade_requests r
        JOIN public.bookings b ON r.original_booking_id = b.booking_id
        WHERE r.status = 'active'
          AND b.status = 'Confirmed'
    LOOP
        -- Check if event is seat-map
        SELECT EXISTS (SELECT 1 FROM public.event_seats WHERE event_id = v_req.event_id) INTO v_is_seat_map;

        IF v_is_seat_map THEN
            -- Check physical seats availability
            SELECT count(*) INTO v_available_seats
            FROM public.event_seats
            WHERE event_id = v_req.event_id 
              AND category = v_req.desired_category
              AND status = 'Available';
        ELSE
            -- Check category inventory
            SELECT available_seats INTO v_available_seats
            FROM public.ticket_categories
            WHERE event_id = v_req.event_id 
              AND category = v_req.desired_category;
        END IF;

        -- If enough seats are available, move status to notified
        IF v_available_seats >= v_req.seats_booked THEN
            UPDATE public.seat_upgrade_requests
            SET status = 'notified', updated_at = now()
            WHERE id = v_req.id;
        END IF;
    END LOOP;
END;
;


-- Atomic lock and claim for upgrade requests
CREATE OR REPLACE FUNCTION public.claim_seat_upgrade(p_request_id uuid, p_user_id text)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
AS 
DECLARE
    v_locked_id uuid;
BEGIN
    -- Atomically lock the row and update to processing if it's currently notified
    -- OR if it's already processing but stale (older than 5 minutes)
    UPDATE public.seat_upgrade_requests
    SET status = 'processing',
        updated_at = now()
    WHERE id = p_request_id 
      AND user_id = p_user_id 
      AND (
          status = 'notified'
          OR (status = 'processing' AND updated_at < now() - interval '5 minutes')
      )
    RETURNING id INTO v_locked_id;

    RETURN v_locked_id IS NOT NULL;
END;
;


-- Process Seat Downgrade (Cheaper Upgrade Flow)
CREATE OR REPLACE FUNCTION public.process_seat_downgrade(p_request_id uuid)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
AS 
DECLARE
    v_req record;
    v_booking record;
    v_new_available integer;
    v_new_price numeric;
    v_is_seat_map boolean;
    v_assigned_seat_ids integer[];
    v_current_physical_seats integer;
BEGIN
    -- Lock request
    SELECT * INTO v_req
    FROM public.seat_upgrade_requests
    WHERE id = p_request_id AND status = 'processing' FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Valid processing request not found';
    END IF;

    -- Lock booking and validate
    SELECT * INTO v_booking
    FROM public.bookings
    WHERE booking_id = v_req.original_booking_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Booking not found';
    END IF;

    IF v_booking.status != 'Confirmed' THEN
        RAISE EXCEPTION 'Booking is not Confirmed';
    END IF;

    IF v_booking.user_id != v_req.user_id THEN
        RAISE EXCEPTION 'Booking user mismatch';
    END IF;
    
    IF v_booking.event_id != v_req.event_id THEN
        RAISE EXCEPTION 'Booking event mismatch';
    END IF;

    IF v_booking.category != v_req.current_category THEN
        RAISE EXCEPTION 'Booking category mismatch';
    END IF;

    IF v_req.desired_category = v_req.current_category THEN
        RAISE EXCEPTION 'Desired category is the same as current category';
    END IF;

    -- 1. Detect if it''s a physical seat-map event
    SELECT EXISTS (SELECT 1 FROM public.event_seats WHERE event_id = v_req.event_id) INTO v_is_seat_map;

    IF v_is_seat_map THEN
        -- 2. Lock & Select desired physical seats FIRST
        WITH to_book AS (
            SELECT id 
            FROM public.event_seats 
            WHERE event_id = v_req.event_id 
              AND category = v_req.desired_category 
              AND status = 'Available'
            ORDER BY seat_row, seat_number
            LIMIT v_booking.seats_booked
            FOR UPDATE SKIP LOCKED
        )
        SELECT array_agg(id) INTO v_assigned_seat_ids FROM to_book;
        
        -- 3. Availability Check
        IF v_assigned_seat_ids IS NULL OR array_length(v_assigned_seat_ids, 1) < v_booking.seats_booked THEN
            RAISE EXCEPTION 'Not enough physical seats available in %', v_req.desired_category;
        END IF;

        -- 4. Count and validate existing physical seats
        SELECT COUNT(*) INTO v_current_physical_seats
        FROM public.event_seats
        WHERE booking_id = v_booking.booking_id;

        IF v_current_physical_seats > 0 AND v_current_physical_seats != v_booking.seats_booked THEN
            RAISE EXCEPTION 'Data inconsistency: Booking has % seats booked but % physical seats assigned', v_booking.seats_booked, v_current_physical_seats;
        END IF;
    END IF;

    -- Lock new category
    SELECT available_seats, price_inr INTO v_new_available, v_new_price
    FROM public.ticket_categories
    WHERE event_id = v_req.event_id AND category = v_req.desired_category FOR UPDATE;

    IF v_new_available < v_booking.seats_booked THEN
        RAISE EXCEPTION 'Not enough seats available in %', v_req.desired_category;
    END IF;

    -- Update categories
    UPDATE public.ticket_categories
    SET available_seats = available_seats - v_booking.seats_booked, updated_at = now()
    WHERE event_id = v_req.event_id AND category = v_req.desired_category;

    UPDATE public.ticket_categories
    SET available_seats = available_seats + v_booking.seats_booked, updated_at = now()
    WHERE event_id = v_req.event_id AND category = v_req.current_category;

    IF v_is_seat_map THEN
        -- 5. Release old seats
        UPDATE public.event_seats
        SET status = 'Available',
            booking_id = NULL,
            locked_by_user_id = NULL,
            locked_at = NULL
        WHERE booking_id = v_booking.booking_id;

        -- 6. Book new seats
        UPDATE public.event_seats
        SET status = 'Booked',
            booking_id = v_booking.booking_id,
            locked_by_user_id = NULL,
            locked_at = NULL
        WHERE id = ANY(v_assigned_seat_ids);
    END IF;

    -- Update booking
    UPDATE public.bookings
    SET category = v_req.desired_category,
        total_amount = v_new_price * v_booking.seats_booked
    WHERE booking_id = v_req.original_booking_id;

    -- Set to refund_pending
    UPDATE public.seat_upgrade_requests
    SET status = 'refund_pending', updated_at = now()
    WHERE id = p_request_id;

    RETURN true;
END;
;


-- Finalize Seat Upgrade (More Expensive - Webhook Flow)
CREATE OR REPLACE FUNCTION public.finalize_seat_upgrade(p_request_id uuid, p_razorpay_payment_id text, p_payment_amount numeric)
RETURNS boolean
LANGUAGE plpgsql
SECURITY DEFINER
AS 
DECLARE
    v_req record;
    v_booking record;
    v_new_available integer;
    v_new_price numeric;
    v_old_price numeric;
    v_expected_diff numeric;
    v_is_seat_map boolean;
    v_assigned_seat_ids integer[];
    v_current_physical_seats integer;
BEGIN
    -- Lock request
    SELECT * INTO v_req
    FROM public.seat_upgrade_requests
    WHERE id = p_request_id AND status = 'payment_pending' FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Valid payment_pending request not found';
    END IF;

    -- Lock booking and validate
    SELECT * INTO v_booking
    FROM public.bookings
    WHERE booking_id = v_req.original_booking_id FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Booking not found';
    END IF;

    IF v_booking.status != 'Confirmed' THEN
        RAISE EXCEPTION 'Booking is not Confirmed';
    END IF;

    IF v_booking.user_id != v_req.user_id THEN
        RAISE EXCEPTION 'Booking user mismatch';
    END IF;
    
    IF v_booking.event_id != v_req.event_id THEN
        RAISE EXCEPTION 'Booking event mismatch';
    END IF;

    IF v_booking.category != v_req.current_category THEN
        RAISE EXCEPTION 'Booking category mismatch';
    END IF;

    IF v_req.desired_category = v_req.current_category THEN
        RAISE EXCEPTION 'Desired category is the same as current category';
    END IF;

    -- Calculate expected amount difference server-side
    SELECT price_inr INTO v_new_price
    FROM public.ticket_categories
    WHERE event_id = v_req.event_id AND category = v_req.desired_category FOR UPDATE;

    SELECT price_inr INTO v_old_price
    FROM public.ticket_categories
    WHERE event_id = v_req.event_id AND category = v_req.current_category FOR UPDATE;

    -- Calculate difference in INR
    v_expected_diff := (v_new_price - v_old_price) * v_booking.seats_booked;

    -- Prevent floating point issues by rounding
    IF round(v_expected_diff, 2) != round(p_payment_amount, 2) THEN
        RAISE EXCEPTION 'Payment amount mismatch. Expected: %, Provided: %', v_expected_diff, p_payment_amount;
    END IF;

    -- 1. Detect if it''s a physical seat-map event
    SELECT EXISTS (SELECT 1 FROM public.event_seats WHERE event_id = v_req.event_id) INTO v_is_seat_map;

    IF v_is_seat_map THEN
        -- 2. Lock & Select desired physical seats FIRST
        WITH to_book AS (
            SELECT id 
            FROM public.event_seats 
            WHERE event_id = v_req.event_id 
              AND category = v_req.desired_category 
              AND status = 'Available'
            ORDER BY seat_row, seat_number
            LIMIT v_booking.seats_booked
            FOR UPDATE SKIP LOCKED
        )
        SELECT array_agg(id) INTO v_assigned_seat_ids FROM to_book;
        
        -- 3. Availability Check
        IF v_assigned_seat_ids IS NULL OR array_length(v_assigned_seat_ids, 1) < v_booking.seats_booked THEN
            RAISE EXCEPTION 'Not enough physical seats available in %', v_req.desired_category;
        END IF;

        -- 4. Count and validate existing physical seats
        SELECT COUNT(*) INTO v_current_physical_seats
        FROM public.event_seats
        WHERE booking_id = v_booking.booking_id;

        IF v_current_physical_seats > 0 AND v_current_physical_seats != v_booking.seats_booked THEN
            RAISE EXCEPTION 'Data inconsistency: Booking has % seats booked but % physical seats assigned', v_booking.seats_booked, v_current_physical_seats;
        END IF;
    END IF;

    -- Check available seats in ticket_categories
    SELECT available_seats INTO v_new_available
    FROM public.ticket_categories
    WHERE event_id = v_req.event_id AND category = v_req.desired_category;

    IF v_new_available < v_booking.seats_booked THEN
        RAISE EXCEPTION 'Not enough seats available in %', v_req.desired_category;
    END IF;

    -- Swap Categories
    UPDATE public.ticket_categories
    SET available_seats = available_seats - v_booking.seats_booked, updated_at = now()
    WHERE event_id = v_req.event_id AND category = v_req.desired_category;

    UPDATE public.ticket_categories
    SET available_seats = available_seats + v_booking.seats_booked, updated_at = now()
    WHERE event_id = v_req.event_id AND category = v_req.current_category;

    IF v_is_seat_map THEN
        -- 5. Release old seats
        UPDATE public.event_seats
        SET status = 'Available',
            booking_id = NULL,
            locked_by_user_id = NULL,
            locked_at = NULL
        WHERE booking_id = v_booking.booking_id;

        -- 6. Book new seats
        UPDATE public.event_seats
        SET status = 'Booked',
            booking_id = v_booking.booking_id,
            locked_by_user_id = NULL,
            locked_at = NULL
        WHERE id = ANY(v_assigned_seat_ids);
    END IF;

    -- Update booking
    UPDATE public.bookings
    SET category = v_req.desired_category,
        total_amount = v_new_price * v_booking.seats_booked,
        razorpay_payment_id = p_razorpay_payment_id
    WHERE booking_id = v_req.original_booking_id;

    -- Insert payment
    INSERT INTO public.payments (payment_id, booking_id, user_id, amount, method, status)
    VALUES (p_razorpay_payment_id, v_booking.booking_id, v_booking.user_id, p_payment_amount, 'Razorpay Upgrade', 'Success')
    ON CONFLICT (payment_id) DO NOTHING;

    -- Set to upgraded
    UPDATE public.seat_upgrade_requests
    SET status = 'upgraded', updated_at = now()
    WHERE id = p_request_id;

    RETURN true;
END;
;


-- Supabase Edge Function Webhook Trigger
-- NOTE: The pg_net trigger was removed for security reasons, as it exposed
-- the Edge Function URL logic and lacked the required Authorization bearer
-- token configuration in source-controlled SQL.
--
-- To configure the upgrade notifications, please create a Supabase Database Webhook
-- via the Supabase Dashboard:
-- 1. Go to Database -> Webhooks
-- 2. Create a new webhook on 'seat_upgrade_requests' table.
-- 3. Trigger on UPDATE.
-- 4. Set condition: old_record.status == ''active'' AND record.status == ''notified''
-- 5. Set Type to HTTP Request, Method POST.
-- 6. URL: https://<PROJECT_REF>.supabase.co/functions/v1/send-booking-notifications
-- 7. Add HTTP Header: Authorization: Bearer <ANON_KEY>

-- Ensure pg_cron is enabled
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Schedule the check_seat_upgrades function to run every 30 minutes
-- (Requires pg_cron extension, usually available in Supabase)
-- Uncomment and run manually in Supabase SQL editor if needed:
-- SELECT cron.schedule('check_seat_upgrades', '*/30 * * * *', 'SELECT public.check_seat_upgrades()');
