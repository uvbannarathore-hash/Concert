from datetime import datetime, timezone
from app.supabase_client import supabase_admin
from app.config import RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET
import razorpay
import json

razorpay_client = razorpay.Client(auth=(RAZORPAY_KEY_ID, RAZORPAY_KEY_SECRET))

# ---------------------------------------------------------------------------
# TEMPORARY DIAGNOSTIC LOGGING (remove once BK1789312609141 is confirmed
# fixed). All lines are prefixed "[CANCEL_DIAG]" so they're easy to grep out
# of logs afterward: grep -v '\[CANCEL_DIAG\]'
# ---------------------------------------------------------------------------
def _diag(label, **kwargs):
    try:
        print(f"[CANCEL_DIAG] {label}: {json.dumps(kwargs, default=str)}")
    except Exception as _e:
        print(f"[CANCEL_DIAG] {label}: <unserializable> {kwargs} (err={_e})")


def get_cancellation_eligibility(booking_id: str, user_id: str) -> dict:
    """
    Evaluates if a booking can be cancelled and calculates the refund amount.
    Returns:
        {
            "eligible": bool,
            "reason": str,
            "refund_percentage": int,
            "cancellation_fee_percentage": int,
            "eligible_amount": float,
            "refund_amount": float,
            "refund_amount_paise": int
        }
    """
    # Fetch booking
    booking_res = (
        supabase_admin.table("bookings")
        .select("*, events(*)")
        .eq("booking_id", booking_id)
        .eq("user_id", user_id)
        .execute()
    )

    if not booking_res.data:
        return {"eligible": False, "reason": "Booking not found or does not belong to the user.", "refund_amount": 0}

    booking = booking_res.data[0]
    event = booking.get("events", {})

    if booking["status"] == "Cancelled":
        return {"eligible": False, "reason": "Booking is already cancelled.", "refund_amount": 0}

    if booking["payment_status"] != "Paid":
        return {"eligible": False, "reason": "Booking is not paid, cancellation and refund are not applicable.", "refund_amount": 0}

    # Time-based policy check
    try:
        # Assuming event_time is "HH:MM" or similar and event_date is "YYYY-MM-DD"
        # We need to construct a timezone-aware datetime for the event in Asia/Kolkata
        from zoneinfo import ZoneInfo
        event_time = event.get('event_time')
        if not event_time:
            event_time = "00:00"
        elif len(event_time) > 5:
            # handle formats like "19:00:00" or AM/PM
            # If it's something like "8:00 PM", we parse it carefully
            try:
                event_time_obj = datetime.strptime(event_time, "%I:%M %p")
                event_time = event_time_obj.strftime("%H:%M")
            except ValueError:
                # Might just be "19:00:00"
                event_time = event_time[:5]

        event_datetime_str = f"{event['event_date']} {event_time}"
        event_dt = datetime.strptime(event_datetime_str, "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    except Exception as e:
        return {"eligible": False, "reason": "Could not determine event time for cancellation policy.", "refund_amount": 0}

    now = datetime.now(ZoneInfo("Asia/Kolkata"))

    if now >= event_dt:
        return {"eligible": False, "reason": "Event has already started or passed.", "refund_amount": 0}

    time_diff = event_dt - now
    minutes_before_event = time_diff.total_seconds() / 60.0

    # Policy rules
    event_type = (event.get("event_type") or "").lower()

    # We allow explicit override via cancellation_allowed field if it exists, otherwise fallback to defaults
    cancellation_allowed = event.get("cancellation_allowed")

    if cancellation_allowed is False:
        return {"eligible": False, "reason": "Cancellation is not allowed for this event.", "refund_amount": 0}

    if cancellation_allowed is None:
        # Defaults
        if event_type != "movie":
            return {"eligible": False, "reason": "Cancellation is not allowed for concerts and live events.", "refund_amount": 0}

    # Movie defaults / allowed cancellations
    if minutes_before_event < 20:
        return {"eligible": False, "reason": "Cancellation is not allowed within 20 minutes of showtime.", "refund_amount": 0}
    elif minutes_before_event < 120:
        refund_percentage = 50
        cancellation_fee_percentage = 50
    else:
        refund_percentage = 75
        cancellation_fee_percentage = 25

    # Determine eligible amount
    amount = booking.get("total_amount")
    if amount is None:
        # Fallback for legacy bookings
        ticket_res = (
            supabase_admin.table("ticket_categories")
            .select("price_inr")
            .eq("event_id", booking["event_id"])
            .eq("category", booking["category"])
            .execute()
        )
        if ticket_res.data:
            amount = float(ticket_res.data[0]["price_inr"]) * booking["seats_booked"]
        else:
            amount = 0.0

    amount = float(amount)
    refund_amount = (amount * refund_percentage) / 100.0
    refund_amount_paise = int(round(refund_amount * 100))

    return {
        "eligible": True,
        "reason": "Eligible for cancellation",
        "refund_percentage": refund_percentage,
        "cancellation_fee_percentage": cancellation_fee_percentage,
        "eligible_amount": amount,
        "refund_amount": round(refund_amount, 2),
        "refund_amount_paise": refund_amount_paise
    }


# ---------------------------------------------------------------------------
# refund_status normalization — the booking row's payment_status follows the
# existing, more granular application convention ("Refunded", "Refund
# Pending", "Refund Initiated", "Refund Failed", "Cancelled",
# "No Refund (100% Fee)", ...). refund_details.refund_status is a smaller,
# human-readable set intentionally distinct from booking status/payment
# status - it must never be "Cancelled" (that's a booking STATUS, not a
# refund outcome).
# ---------------------------------------------------------------------------
def _normalize_refund_status(payment_status_value: str) -> str:
    mapping = {
        "Refunded": "Refund Completed",
        "Refund Pending": "Refund Pending",
        "Refund Initiated": "Refund Pending",
        "Refund Failed": "Refund Failed",
        "Cancelled": "No Refund",
        "No Refund (100% Fee)": "No Refund",
    }
    return mapping.get(payment_status_value, "No Refund")


def _db_status_for_refund(rzp_status: str) -> str:
    """Maps a raw Razorpay refund status onto our payment_status vocabulary."""
    if rzp_status == "processed":
        return "Refunded"
    if rzp_status == "pending":
        return "Refund Pending"
    # "created", "queued", or anything else Razorpay might introduce
    return "Refund Initiated"


def _fetch_payment_and_refunds(payment_id: str):
    """
    Fetches the payment plus its FULL refund list from Razorpay's authoritative
    refund endpoint. payment.fetch() alone is not guaranteed to enumerate every
    refund, so we explicitly call the payment-refunds listing API
    (client.payment.fetch_multiple_refund) rather than trusting a "refunds"
    key that may be absent/partial on the payment entity.
    """
    payment_info = razorpay_client.payment.fetch(payment_id)
    _diag(
        "payment.fetch() result",
        payment_id=payment_id,
        status=payment_info.get("status"),
        amount=payment_info.get("amount"),
        amount_refunded=payment_info.get("amount_refunded"),
        refund_status_field=payment_info.get("refund_status"),
    )
    try:
        refunds_resp = razorpay_client.payment.fetch_multiple_refund(payment_id, {"count": 100})
        _diag(
            "fetch_multiple_refund() raw response",
            payment_id=payment_id,
            type=type(refunds_resp).__name__,
            raw=refunds_resp,
        )
        if isinstance(refunds_resp, dict):
            refunds_list = refunds_resp.get("items", [])
        elif isinstance(refunds_resp, list):
            # Defensive: some SDK/gateway versions or mocked clients may
            # return the list directly rather than {"entity","count","items"}.
            refunds_list = refunds_resp
        else:
            refunds_list = []
    except Exception as e:
        _diag("fetch_multiple_refund() raised - falling back to payment_info['refunds']", payment_id=payment_id, error=str(e))
        # Fall back to whatever (possibly partial) refund info payment.fetch()
        # itself carries, rather than failing the whole reconciliation.
        refunds_list = payment_info.get("refunds", []) or []

    _diag(
        "normalized refunds_list",
        payment_id=payment_id,
        count=len(refunds_list),
        refunds=[
            {"id": r.get("id"), "amount": r.get("amount"), "status": r.get("status"), "created_at": r.get("created_at")}
            for r in refunds_list
        ],
    )
    return payment_info, refunds_list


def _reconcile_refund_state(payment_info: dict, refunds_list: list, desired_refund_amount: int) -> dict:
    """
    Determines the true refund state for a payment from Razorpay's
    authoritative data, combining:
      - the explicit refund list (client.payment.fetch_multiple_refund)
      - the payment entity's own `amount_refunded` counter, as an
        independent consistency check (per Razorpay, this reflects the
        total amount refunded against the payment regardless of how many
        refund objects exist).
    All amounts are in paise (Razorpay's smallest currency sub-unit).
    """
    captured_amount = payment_info.get("amount") or 0
    amount_refunded_field = payment_info.get("amount_refunded") or 0

    # Only "processed"/"pending" refunds represent money actually moving or
    # committed to move; "failed"/"cancelled" refund attempts don't count
    # against the payment.
    active_refunds = [r for r in refunds_list if r.get("status") in ("processed", "pending")]
    sum_active_refunds = sum(r.get("amount", 0) or 0 for r in active_refunds)

    # Use the max of the two independent sources as the authoritative
    # "already refunded" figure - protects against either source lagging.
    actual_refunded_amount = max(sum_active_refunds, amount_refunded_field)
    remaining_refundable_amount = max(captured_amount - actual_refunded_amount, 0)

    # Find a refund that (on its own or as the largest on record) already
    # covers the amount we'd otherwise be requesting.
    matching_refund = None
    if active_refunds:
        candidates = sorted(active_refunds, key=lambda r: r.get("amount", 0) or 0, reverse=True)
        for r in candidates:
            if (r.get("amount", 0) or 0) >= desired_refund_amount:
                matching_refund = r
                break
        if matching_refund is None:
            # No single refund covers the desired amount, but refunds do
            # exist (e.g. a partial refund already went out) - surface the
            # most recent one as the reference for reconciliation/reuse.
            matching_refund = max(active_refunds, key=lambda r: r.get("created_at", 0) or 0)

    _diag(
        "reconcile_refund_state result",
        captured_amount=captured_amount,
        amount_refunded_field=amount_refunded_field,
        sum_active_refunds=sum_active_refunds,
        active_refund_count=len(active_refunds),
        actual_refunded_amount_paise=actual_refunded_amount,
        requested_refund_amount_paise=desired_refund_amount,
        remaining_refundable_amount_paise=remaining_refundable_amount,
        matching_refund=(
            {"id": matching_refund.get("id"), "amount": matching_refund.get("amount"), "status": matching_refund.get("status")}
            if matching_refund else None
        ),
    )

    return {
        "captured_amount": captured_amount,
        "actual_refunded_amount": actual_refunded_amount,
        "remaining_refundable_amount": remaining_refundable_amount,
        "matching_refund": matching_refund,
    }


def initiate_cancellation(booking_id: str, user_id: str) -> dict:
    """Centralised cancellation/refund workflow used by both frontend and AI paths.
    Returns a dict mirroring the former cancel_booking endpoint response.
    """
    # Verify ownership and fetch current state
    booking_check = (
        supabase_admin.table("bookings")
        .select("*, events(*)")
        .eq("booking_id", booking_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not booking_check.data:
        return {"success": False, "message": "Booking not found or it does not belong to this user."}
    booking = booking_check.data[0]
    # Idempotent cases
    if booking["status"] == "Cancelled":
        return {
            "success": True,
            "message": f"Booking {booking_id} is already cancelled",
            "payment_status": booking.get("payment_status"),
            "refund_details": booking.get("refund_details"),
        }
    if booking.get("payment_status") == "Cancellation Processing":
        return {
            "success": True,
            "message": "Cancellation is currently processing",
            "payment_status": "Cancellation Processing",
        }
    # Eligibility calculation
    eligibility = get_cancellation_eligibility(booking_id, user_id)
    if not eligibility["eligible"]:
        return {"success": False, "message": f"Cannot cancel booking: {eligibility['reason']}"}
    # Atomic claim
    claim = (
        supabase_admin.table("bookings")
        .update({"payment_status": "Cancellation Processing"})
        .eq("booking_id", booking_id)
        .eq("user_id", user_id)
        .neq("status", "Cancelled")
        .neq("payment_status", "Cancellation Processing")
        .execute()
    )
    if not claim.data:
        refreshed = (
            supabase_admin.table("bookings")
            .select("status", "payment_status", "refund_details")
            .eq("booking_id", booking_id)
            .eq("user_id", user_id)
            .execute()
        )
        if refreshed.data:
            row = refreshed.data[0]
            if row["status"] == "Cancelled":
                return {"success": True, "message": f"Booking {booking_id} is already cancelled", "payment_status": row.get("payment_status"), "refund_details": row.get("refund_details")}
            return {"success": True, "message": "Cancellation is currently processing", "payment_status": row.get("payment_status")}
        return {"success": False, "message": "Unable to claim cancellation. Please retry."}

    # ------------------------------------------------------------------
    # Razorpay refund logic - amount-aware reconciliation.
    #
    # requested_refund_amount = policy-calculated amount (eligibility)
    # actual_refunded_amount  = what Razorpay confirms is actually refunded
    # These are tracked separately and must never be conflated.
    # ------------------------------------------------------------------
    db_payment_status = "Cancelled"
    refund_id = None
    error_message = None
    requested_refund_amount_paise = eligibility["refund_amount_paise"]
    actual_refunded_amount_paise = 0
    remaining_refundable_amount_paise = None  # unknown until we fetch the payment

    if booking.get("razorpay_payment_id") and requested_refund_amount_paise > 0:
        payment_id = booking["razorpay_payment_id"]
        try:
            payment_info, refunds_list = _fetch_payment_and_refunds(payment_id)
            payment_status = payment_info.get("status")
            captured_amount = payment_info.get("amount") or 0

            recon = _reconcile_refund_state(payment_info, refunds_list, requested_refund_amount_paise)
            actual_refunded_amount_paise = recon["actual_refunded_amount"]
            remaining_refundable_amount_paise = recon["remaining_refundable_amount"]
            matching_refund = recon["matching_refund"]

            if actual_refunded_amount_paise >= requested_refund_amount_paise and matching_refund is not None:
                _diag("branch selected", booking_id=booking_id, branch="REUSE_EXISTING_REFUND (no new refund call)")
                # Already fully covered by an existing refund (or refunds) -
                # reuse it, and NEVER call payment.refund() again.
                refund_id = matching_refund.get("id")
                db_payment_status = _db_status_for_refund(matching_refund.get("status"))

            elif payment_status == "captured" and remaining_refundable_amount_paise > 0:
                _diag(
                    "branch selected",
                    booking_id=booking_id,
                    branch="CREATE_NEW_REFUND (captured, remaining>0)",
                    actual_refunded_amount_paise=actual_refunded_amount_paise,
                    requested_refund_amount_paise=requested_refund_amount_paise,
                    remaining_refundable_amount_paise=remaining_refundable_amount_paise,
                )
                # Only refund the outstanding remainder, capped so we can
                # never exceed what Razorpay will actually allow.
                outstanding = requested_refund_amount_paise - actual_refunded_amount_paise
                refund_amount = min(outstanding, remaining_refundable_amount_paise)
                try:
                    refund = razorpay_client.payment.refund(
                        payment_id,
                        {"amount": refund_amount, "notes": {"booking_id": booking_id, "reason": "user_cancelled"}},
                    )
                    refund_id = refund.get("id") if isinstance(refund, dict) else None
                    rzp_status = refund.get("status") if isinstance(refund, dict) else None
                    actual_refunded_amount_paise += refund_amount
                    remaining_refundable_amount_paise -= refund_amount
                except Exception as refund_err:
                    # The API call raised, but Razorpay may have still
                    # created the refund on their side (ambiguous
                    # network/timeout error). Re-fetch and reconcile before
                    # concluding it actually failed.
                    payment_info2, refunds_list2 = _fetch_payment_and_refunds(payment_id)
                    recon2 = _reconcile_refund_state(payment_info2, refunds_list2, requested_refund_amount_paise)
                    if recon2["actual_refunded_amount"] > actual_refunded_amount_paise and recon2["matching_refund"] is not None:
                        refund_id = recon2["matching_refund"].get("id")
                        rzp_status = recon2["matching_refund"].get("status")
                        actual_refunded_amount_paise = recon2["actual_refunded_amount"]
                        remaining_refundable_amount_paise = recon2["remaining_refundable_amount"]
                    else:
                        raise refund_err
                db_payment_status = _db_status_for_refund(rzp_status)

            elif payment_status == "authorized":
                _diag("branch selected", booking_id=booking_id, branch="CAPTURE_THEN_REFUND (authorized)")
                # Capture then attempt refund
                try:
                    razorpay_client.payment.capture(payment_id, captured_amount)
                except Exception as cap_err:
                    raise Exception(f"Capture failed: {cap_err}")
                # Re-fetch after capture and re-reconcile from scratch
                payment_info, refunds_list = _fetch_payment_and_refunds(payment_id)
                payment_status = payment_info.get("status")
                recon = _reconcile_refund_state(payment_info, refunds_list, requested_refund_amount_paise)
                actual_refunded_amount_paise = recon["actual_refunded_amount"]
                remaining_refundable_amount_paise = recon["remaining_refundable_amount"]

                if payment_status == "captured" and remaining_refundable_amount_paise > 0:
                    outstanding = requested_refund_amount_paise - actual_refunded_amount_paise
                    refund_amount = min(outstanding, remaining_refundable_amount_paise)
                    try:
                        refund = razorpay_client.payment.refund(
                            payment_id,
                            {"amount": refund_amount, "notes": {"booking_id": booking_id, "reason": "user_cancelled"}},
                        )
                        refund_id = refund.get("id") if isinstance(refund, dict) else None
                        rzp_status = refund.get("status") if isinstance(refund, dict) else None
                        actual_refunded_amount_paise += refund_amount
                        remaining_refundable_amount_paise -= refund_amount
                        db_payment_status = _db_status_for_refund(rzp_status)
                    except Exception as refund_err:
                        payment_info2, refunds_list2 = _fetch_payment_and_refunds(payment_id)
                        recon2 = _reconcile_refund_state(payment_info2, refunds_list2, requested_refund_amount_paise)
                        if recon2["actual_refunded_amount"] > actual_refunded_amount_paise and recon2["matching_refund"] is not None:
                            refund_id = recon2["matching_refund"].get("id")
                            actual_refunded_amount_paise = recon2["actual_refunded_amount"]
                            remaining_refundable_amount_paise = recon2["remaining_refundable_amount"]
                            db_payment_status = _db_status_for_refund(recon2["matching_refund"].get("status"))
                        else:
                            db_payment_status = "Refund Failed"
                            error_message = str(refund_err)
                elif actual_refunded_amount_paise >= requested_refund_amount_paise and recon["matching_refund"] is not None:
                    refund_id = recon["matching_refund"].get("id")
                    db_payment_status = _db_status_for_refund(recon["matching_refund"].get("status"))
                else:
                    db_payment_status = "Refund Failed"
                    error_message = f"Payment not captured after capture attempt (status: {payment_status})"
            else:
                _diag(
                    "branch selected",
                    booking_id=booking_id,
                    branch="NOT_ELIGIBLE (payment_status not captured/authorized, and not already covered)",
                    payment_status=payment_status,
                    actual_refunded_amount_paise=actual_refunded_amount_paise,
                    requested_refund_amount_paise=requested_refund_amount_paise,
                    matching_refund_present=matching_refund is not None,
                )
                db_payment_status = "Refund Failed"
                error_message = f"Payment status {payment_status} not eligible for refund"
        except Exception as e:
            # Last-resort reconciliation before giving up: it's possible the
            # refund actually went through and only our own call raised.
            try:
                payment_info, refunds_list = _fetch_payment_and_refunds(booking["razorpay_payment_id"])
                recon = _reconcile_refund_state(payment_info, refunds_list, requested_refund_amount_paise)
                if recon["matching_refund"] is not None and recon["actual_refunded_amount"] > 0:
                    refund_id = recon["matching_refund"].get("id")
                    actual_refunded_amount_paise = recon["actual_refunded_amount"]
                    remaining_refundable_amount_paise = recon["remaining_refundable_amount"]
                    db_payment_status = _db_status_for_refund(recon["matching_refund"].get("status"))
                else:
                    db_payment_status = "Refund Failed"
                    error_message = str(e)
            except Exception:
                db_payment_status = "Refund Failed"
                error_message = str(e)
            print(f"Razorpay refund error for booking {booking_id}: {e}")
    elif requested_refund_amount_paise == 0 and booking.get("razorpay_payment_id"):
        db_payment_status = "No Refund (100% Fee)"
    else:
        db_payment_status = "Cancelled"

    refund_status_norm = _normalize_refund_status(db_payment_status)

    refund_details = {
        "eligible_amount": eligibility["eligible_amount"],
        "refund_percentage": eligibility["refund_percentage"],
        "cancellation_fee_percentage": eligibility["cancellation_fee_percentage"],
        "requested_refund_amount": round(requested_refund_amount_paise / 100.0, 2),
        "actual_refunded_amount": round(actual_refunded_amount_paise / 100.0, 2),
        "remaining_refundable_amount": (
            round(remaining_refundable_amount_paise / 100.0, 2)
            if remaining_refundable_amount_paise is not None
            else None
        ),
        "refund_status": refund_status_norm,
        "refund_id": refund_id,
    }
    if error_message:
        refund_details["error_message"] = error_message

    # Final update — status, payment_status, and the fully-populated
    # refund_details all land in ONE update so the DB never has a moment
    # where refund_details is stale/partial relative to status. This is
    # also the write the existing Postgres trigger watches for the
    # Confirmed -> Cancelled transition (we never call the Edge Function
    # directly). Guarded so it only takes effect if this request is still
    # the one holding the "Cancellation Processing" claim for this exact
    # user's booking - if that's no longer true (e.g. a concurrent request
    # finished first), we do NOT report a fresh success here.
    update_payload = {
        "status": "Cancelled",
        "payment_status": db_payment_status,
        "refund_details": refund_details,
    }
    final_update = (
        supabase_admin.table("bookings")
        .update(update_payload)
        .eq("booking_id", booking_id)
        .eq("user_id", user_id)
        .eq("payment_status", "Cancellation Processing")
        .execute()
    )

    if not final_update.data:
        # We held the claim a moment ago but the row no longer matches it -
        # someone/something else already finished (or reset) this
        # cancellation. Report the actual current state instead of a fresh
        # success, so we never silently overwrite or double-report.
        refreshed = (
            supabase_admin.table("bookings")
            .select("status, payment_status, refund_details")
            .eq("booking_id", booking_id)
            .eq("user_id", user_id)
            .execute()
        )
        if refreshed.data:
            row = refreshed.data[0]
            if row["status"] == "Cancelled":
                return {
                    "success": True,
                    "message": f"Booking {booking_id} is already cancelled",
                    "payment_status": row.get("payment_status"),
                    "refund_details": row.get("refund_details"),
                }
            return {
                "success": True,
                "message": "Cancellation is currently processing",
                "payment_status": row.get("payment_status"),
            }
        return {"success": False, "message": "Unable to finalize cancellation. Please retry."}

    # Amendment 5: Reward Revocation
    # If this was a group booking that issued a reward, revoke it.
    try:
        session_res = supabase_admin.table("group_booking_sessions").select("id").eq("booking_id", booking_id).execute()
        if session_res.data:
            session_id = session_res.data[0]["id"]
            supabase_admin.table("coupons").update({"is_active": False}).eq("source_group_session_id", session_id).execute()
    except Exception as e:
        print(f"Failed to revoke group booking reward for {booking_id}: {e}")

    return {
        "success": True,
        "message": f"Booking {booking_id} cancelled",
        "refund_status": refund_status_norm,
        "refund_amount": eligibility["refund_amount"],
        "refund_details": refund_details,
        "payment_status": db_payment_status,
    }