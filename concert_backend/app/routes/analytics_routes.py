from fastapi import APIRouter, Depends
from app.admin_auth import get_current_admin
from app.services import analytics_service

router = APIRouter(prefix="/admin/analytics", tags=["admin_analytics"])

@router.get("/overview")
def get_analytics_overview(admin=Depends(get_current_admin)):
    return analytics_service.get_overview_metrics()

@router.get("/revenue")
def get_analytics_revenue(admin=Depends(get_current_admin)):
    return analytics_service.get_revenue_over_time()

@router.get("/bookings")
def get_analytics_bookings(admin=Depends(get_current_admin)):
    return analytics_service.get_bookings_over_time()

@router.get("/top-events")
def get_analytics_top_events(admin=Depends(get_current_admin)):
    return analytics_service.get_top_events()

@router.get("/category-sales")
def get_analytics_category_sales(admin=Depends(get_current_admin)):
    return analytics_service.get_category_sales()
