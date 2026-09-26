from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone

def round_money(amount: float | Decimal) -> Decimal:
    """
    Rounds all money to 2 decimals using round-half-up (ROUND_HALF_UP).
    This ensures consistent financial math across the system.
    """
    return Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

PLAN_TIER_RATES = {
    "starter": Decimal('0.05'),
    "pro": Decimal('0.03'),
    "business": Decimal('0.015')
}

def get_commission_pct(organizer: dict) -> Decimal:
    """
    Determines the organizer's commission rate based on their plan tier.
    Falls back to 5% (Starter) if the plan has expired or isn't set.
    """
    plan_tier = (organizer.get("plan_tier") or "starter").lower()
    plan_expiry_date_str = organizer.get("plan_expiry_date")
    
    
    base_rate = PLAN_TIER_RATES.get(plan_tier, Decimal('0.05'))
    
    if plan_tier in ["pro", "business"] and plan_expiry_date_str:
        try:
            # Parse expiry date and check against current time
            expiry_date = datetime.fromisoformat(plan_expiry_date_str)
            if expiry_date.tzinfo is None:
                expiry_date = expiry_date.replace(tzinfo=timezone.utc)
            
            if expiry_date >= datetime.now(timezone.utc):
                return base_rate
        except ValueError:
            pass # fallback to 5%
            
    return Decimal('0.05')  # Starter fallback
