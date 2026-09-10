CREATE OR REPLACE FUNCTION public.book_ticket_transaction(p_booking_id text, p_user_id text, p_event_id text, p_category text, p_seats_booked integer)
 RETURNS json
 LANGUAGE plpgsql
AS $function$
DECLARE
    v_available_seats integer;
    v_booking_date date;
    v_is_admin boolean;
    v_name text;
    v_email text;
    v_phone text;
BEGIN
    -- Guard: admins cannot book tickets
    SELECT is_admin, name, email, phone
    INTO v_is_admin, v_name, v_email, v_phone
    FROM users
    WHERE user_id = p_user_id;

    IF v_is_admin IS TRUE THEN
        RAISE EXCEPTION 'Admin accounts cannot book tickets. Please use a regular user account.';
    END IF;

    -- Lock the ticket category row
    SELECT available_seats
    INTO v_available_seats
    FROM ticket_categories
    WHERE event_id = p_event_id
      AND category = p_category
    FOR UPDATE;

    -- Category does not exist
    IF v_available_seats IS NULL THEN
        RAISE EXCEPTION 'Ticket category not found';
    END IF;

    -- Not enough seats
    IF v_available_seats < p_seats_booked THEN
        RAISE EXCEPTION 'Not enough seats available';
    END IF;

    -- Current booking date
    v_booking_date := current_date;

    -- Create booking as Pending (not Confirmed) - waiting on the
    -- Razorpay Payment Link to be paid
    INSERT INTO bookings (
        booking_id,
        user_id,
        event_id,
        category,
        seats_booked,
        booking_date,
        status,
        payment_status,
        created_at
    )
    VALUES (
        p_booking_id,
        p_user_id,
        p_event_id,
        p_category,
        p_seats_booked,
        v_booking_date,
        'Pending',
        'Pending',
        now()
    );

    -- Reserve seats now
    UPDATE ticket_categories
    SET available_seats = available_seats - p_seats_booked,
        updated_at = now()
    WHERE event_id = p_event_id
      AND category = p_category;

    RETURN json_build_object(
        'success', true,
        'booking_id', p_booking_id,
        'event_id', p_event_id,
        'category', p_category,
        'seats_booked', p_seats_booked,
        'remaining_seats', v_available_seats - p_seats_booked,
        'status', 'Pending',
        'payment_status', 'Pending',
        'customer_name', v_name,
        'customer_email', v_email,
        'customer_phone', v_phone
    );

EXCEPTION
    WHEN OTHERS THEN
        RAISE;
END;
$function$;
