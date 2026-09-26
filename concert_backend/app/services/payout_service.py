from app.supabase_client import supabase_admin

def has_valid_payout_destination(user_id: str) -> bool:
    """
    Checks if a user has configured a valid payout destination (UPI ID or Bank Account + IFSC).
    Returns True if valid, False otherwise.
    """
    user_res = supabase_admin.table("users").select("payout_upi_id, payout_bank_account, payout_ifsc").eq("user_id", user_id).execute()
    if not user_res.data:
        return False
        
    row = user_res.data[0]
    
    # Check UPI ID
    if row.get("payout_upi_id"):
        return True
        
    # Check Bank Account and IFSC (both must be present if using bank transfer)
    if row.get("payout_bank_account") and row.get("payout_ifsc"):
        return True
        
    return False
