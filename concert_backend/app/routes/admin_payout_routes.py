from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Literal
from datetime import datetime, timezone
from app.admin_auth import get_current_admin
from app.supabase_client import supabase_admin

router = APIRouter(prefix="/admin/payouts", tags=["admin_payouts"])

class MarkPaidRequest(BaseModel):
    ledger_type: Literal['booking', 'resale']
    ledger_ids: List[str]

@router.get("")
def list_payouts(admin: dict = Depends(get_current_admin)):
    """
    Returns pending and paid payouts from both booking_ledger and resale_ledger.
    """
    # 1. Fetch from booking_ledger
    booking_res = supabase_admin.table('booking_ledger').select(
        'booking_id, organizer_payout, payout_status, created_at, bookings(event_id, events(organizer_id))'
    ).execute()
    
    # 2. Fetch from resale_ledger
    resale_res = supabase_admin.table('resale_ledger').select(
        'resale_booking_id, seller_payout, payout_status, created_at, seller_id'
    ).execute()

    # Collect user IDs to fetch profiles
    user_ids = set()
    for b in booking_res.data:
        org_id = b.get('bookings', {}).get('events', {}).get('organizer_id')
        if org_id:
            user_ids.add(org_id)
            
    for r in resale_res.data:
        seller_id = r.get('seller_id')
        if seller_id:
            user_ids.add(seller_id)
            
    # Fetch users (instead of profiles)
    profiles_dict = {}
    if user_ids:
        profiles_res = supabase_admin.table('users').select('user_id, name, payout_upi_id, payout_bank_account, payout_ifsc').in_('user_id', list(user_ids)).execute()
        for p in profiles_res.data:
            profiles_dict[p['user_id']] = p

    payouts = []

    # Process booking ledger
    for b in booking_res.data:
        event_info = b.get('bookings', {}).get('events', {})
        if not event_info:
            continue
        org_id = event_info.get('organizer_id')
        profile = profiles_dict.get(org_id, {})
        
        payout_dest = None
        if profile.get('payout_upi_id') or profile.get('payout_bank_account'):
            payout_dest = {
                "upi_id": profile.get("payout_upi_id"),
                "bank_account": profile.get("payout_bank_account"),
                "ifsc": profile.get("payout_ifsc")
            }
        
        payouts.append({
            "id": b['booking_id'],
            "ledger_type": "booking",
            "amount": b['organizer_payout'],
            "status": "pending" if b['payout_status'] == 'awaiting_payment' else b['payout_status'],
            "created_at": b['created_at'],
            "recipient_name": profile.get('name', 'Unknown Organizer'),
            "recipient_id": org_id,
            "payout_destination": payout_dest
        })

    # Process resale ledger
    for r in resale_res.data:
        seller_id = r.get('seller_id')
        profile = profiles_dict.get(seller_id, {})
        
        payout_dest = None
        if profile.get('payout_upi_id') or profile.get('payout_bank_account'):
            payout_dest = {
                "upi_id": profile.get("payout_upi_id"),
                "bank_account": profile.get("payout_bank_account"),
                "ifsc": profile.get("payout_ifsc")
            }

        payouts.append({
            "id": r['resale_booking_id'],
            "ledger_type": "resale",
            "amount": r['seller_payout'],
            "status": "pending" if r['payout_status'] == 'awaiting_payment' else r['payout_status'],
            "created_at": r['created_at'],
            "recipient_name": profile.get('name', 'Unknown Seller'),
            "recipient_id": seller_id,
            "payout_destination": payout_dest
        })

    # Sort by created_at desc
    payouts.sort(key=lambda x: x['created_at'], reverse=True)
    return {"results": payouts}

@router.post("/mark-paid")
def mark_payouts_paid(req: MarkPaidRequest, admin: dict = Depends(get_current_admin)):
    now = datetime.now(timezone.utc).isoformat()
    updated_count = 0

    if req.ledger_type == 'booking':
        for b_id in req.ledger_ids:
            res = supabase_admin.table('booking_ledger').update({
                'payout_status': 'paid',
                'updated_at': now
            }).eq('booking_id', b_id).execute()
            if res.data:
                updated_count += len(res.data)

    elif req.ledger_type == 'resale':
        for r_id in req.ledger_ids:
            res = supabase_admin.table('resale_ledger').update({
                'payout_status': 'paid'
            }).eq('resale_booking_id', r_id).execute()
            if res.data:
                updated_count += len(res.data)

    return {"message": f"Successfully marked {updated_count} payouts as paid.", "updated_count": updated_count}
