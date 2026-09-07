"""
Phase 7 Analytics & Historical Data Router.
Exposes real platform metrics, scoped association analytics, worker utilization,
service demand, matching engine performance audits, CSV exports, and ML dataset foundations.
"""
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status, Response
from fastapi.responses import PlainTextResponse

from app.core.dependencies import get_current_user, require_role
from app.services.analytics_service import (
    get_platform_kpis,
    get_association_analytics,
    calculate_worker_utilization,
    get_service_demand_analytics,
    get_matching_performance_analytics,
    get_geographic_demand_analytics,
    get_ml_worker_ranking_dataset,
    get_ml_demand_forecast_dataset,
    validate_historical_data_quality,
    generate_analytics_csv
)
from app.db.in_memory_store import _COOPERATIVES_BY_ID

logger = logging.getLogger("analytics_router")

router = APIRouter(prefix="/analytics", tags=["Phase 7 Platform & Operational Analytics"])

def _enforce_coop_access(current_user: dict, requested_coop_id: Optional[str]) -> Optional[str]:
    """
    Enforces multi-tenant data isolation.
    - Super Admin can access any cooperative or platform-wide (None).
    - Association Head is strictly restricted to their designated cooperative_id.
    """
    user_role = (current_user.get("role") or current_user.get("token_role") or "").lower()
    user_coop = current_user.get("cooperative_id")

    if user_role == "super_admin":
        return requested_coop_id

    if user_role in ["cooperative_association_head", "admin"]:
        if not user_coop:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is not affiliated with any Cooperative Society."
            )
        if requested_coop_id and str(requested_coop_id) != str(user_coop):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. You are authorized only for Cooperative Society '{user_coop}'."
            )
        return str(user_coop)

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Access restricted to authorized Administrative roles."
    )

# ---------------------------------------------------------------------------
# 1. Super Admin Platform KPIs
# ---------------------------------------------------------------------------
@router.get("/platform")
def get_platform_analytics(
    range_type: str = Query("last_30_days", description="today, last_7_days, last_30_days, this_month, all_time, custom"),
    start_date: Optional[str] = Query(None, description="ISO-8601 start date for custom range"),
    end_date: Optional[str] = Query(None, description="ISO-8601 end date for custom range"),
    current_user: dict = Depends(require_role(["super_admin"]))
):
    """
    Platform-wide KPI aggregation across 5-role users, cooperatives, services,
    bookings, financial GMV, captured amounts, settlements, and dispute resolution.
    """
    return get_platform_kpis(
        range_type=range_type,
        start_date=start_date,
        end_date=end_date
    )

# ---------------------------------------------------------------------------
# 2. Scoped Association Analytics
# ---------------------------------------------------------------------------
@router.get("/association/{cooperative_id}")
def get_association_scoped_analytics(
    cooperative_id: str,
    range_type: str = Query("last_30_days", description="today, last_7_days, last_30_days, this_month, all_time, custom"),
    start_date: Optional[str] = Query(None, description="ISO-8601 start date for custom range"),
    end_date: Optional[str] = Query(None, description="ISO-8601 end date for custom range"),
    current_user: dict = Depends(require_role(["cooperative_association_head", "super_admin"]))
):
    """
    Operational analytics for a specific cooperative society.
    Strictly isolated: Association Head can ONLY access their own cooperative.
    """
    coop_id = _enforce_coop_access(current_user, cooperative_id)
    return get_association_analytics(
        cooperative_id=coop_id or cooperative_id,
        range_type=range_type,
        start_date=start_date,
        end_date=end_date
    )

# ---------------------------------------------------------------------------
# 3. Service Demand Analytics
# ---------------------------------------------------------------------------
@router.get("/services")
def get_services_demand(
    cooperative_id: Optional[str] = Query(None, description="Filter by cooperative (Super Admin or self)"),
    range_type: str = Query("last_30_days", description="today, last_7_days, last_30_days, this_month, all_time, custom"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: dict = Depends(require_role(["super_admin", "cooperative_association_head"]))
):
    """
    Analyzes booking volume per service, per category, peak hours (0–23), peak days, and emergency ratio.
    """
    coop_id = _enforce_coop_access(current_user, cooperative_id)
    return get_service_demand_analytics(
        cooperative_id=coop_id,
        range_type=range_type,
        start_date=start_date,
        end_date=end_date
    )

# ---------------------------------------------------------------------------
# 4. Worker Utilization Analytics
# ---------------------------------------------------------------------------
@router.get("/workers")
def get_workers_utilization(
    cooperative_id: Optional[str] = Query(None, description="Filter by cooperative"),
    range_type: str = Query("last_30_days"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    search: Optional[str] = Query(None, description="Search worker name or skill"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(require_role(["super_admin", "cooperative_association_head"]))
):
    """
    Worker utilization analytics: actual working time vs available time,
    acceptance/completion rates, average duration, average travel distance, and active workload.
    """
    coop_id = _enforce_coop_access(current_user, cooperative_id)
    all_workers = calculate_worker_utilization(cooperative_id=coop_id)

    if search:
        s = search.lower()
        all_workers = [
            w for w in all_workers
            if s in (w.get("worker_name") or "").lower() or s in (w.get("skill") or "").lower()
        ]

    total_count = len(all_workers)
    offset = (page - 1) * limit
    paged = all_workers[offset:offset + limit]

    return {
        "success": True,
        "total_workers": total_count,
        "page": page,
        "limit": limit,
        "workers": paged
    }

# ---------------------------------------------------------------------------
# 5. Privacy-Preserving Geographic Demand Analytics
# ---------------------------------------------------------------------------
@router.get("/demand")
def get_geographic_demand(
    cooperative_id: Optional[str] = Query(None),
    range_type: str = Query("last_30_days"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    current_user: dict = Depends(require_role(["super_admin", "cooperative_association_head"]))
):
    """
    Aggregates booking demand by district and locality.
    Zero leakage: never exposes exact customer street addresses or raw GPS traces.
    """
    coop_id = _enforce_coop_access(current_user, cooperative_id)
    return get_geographic_demand_analytics(
        cooperative_id=coop_id,
        range_type=range_type,
        start_date=start_date,
        end_date=end_date
    )

# ---------------------------------------------------------------------------
# 6. Matching Performance Analytics
# ---------------------------------------------------------------------------
@router.get("/matching")
def get_matching_analytics(
    cooperative_id: Optional[str] = Query(None),
    range_type: str = Query("last_30_days"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = Depends(require_role(["super_admin", "cooperative_association_head"]))
):
    """
    Matching engine audit logs and performance statistics.
    Tracks eligibility filter pass/rejection reasons, ranking scores, and assignment outcomes.
    """
    coop_id = _enforce_coop_access(current_user, cooperative_id)
    return get_matching_performance_analytics(
        cooperative_id=coop_id,
        range_type=range_type,
        start_date=start_date,
        end_date=end_date,
        page=page,
        limit=limit
    )

# ---------------------------------------------------------------------------
# 7. ML Dataset Endpoints (Phase 8 ML Foundation)
# ---------------------------------------------------------------------------
@router.get("/ml-dataset/worker-ranking")
def get_worker_ranking_dataset(
    current_user: dict = Depends(require_role(["super_admin"]))
):
    """
    Extracts the feature vector dataset for training the Phase 8 Worker Ranking ML model.
    Guaranteed zero target leakage.
    """
    return get_ml_worker_ranking_dataset()

@router.get("/ml-dataset/demand-forecast")
def get_demand_forecast_dataset(
    current_user: dict = Depends(require_role(["super_admin"]))
):
    """
    Extracts historical hourly/daily demand time-series dataset for Phase 8 Demand Forecasting ML.
    """
    return get_ml_demand_forecast_dataset()

# ---------------------------------------------------------------------------
# 8. Data Quality Validator Report
# ---------------------------------------------------------------------------
@router.get("/data-quality")
def get_data_quality_report(
    current_user: dict = Depends(require_role(["super_admin"]))
):
    """
    Performs data quality and historical anomaly checks across bookings, assignments, and payments.
    """
    return validate_historical_data_quality()

# ---------------------------------------------------------------------------
# 9. CSV Operational Data Export
# ---------------------------------------------------------------------------
@router.get("/export/csv")
def export_analytics_csv(
    type: str = Query("worker_utilization", description="worker_utilization, service_demand, matching_history, ml_ranking_features, platform_kpis"),
    cooperative_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_role(["super_admin", "cooperative_association_head"]))
):
    """
    Exports clean, authorized operational analytics to CSV format.
    Sanitizes all sensitive tokens, credentials, and raw GPS traces.
    """
    user_role = (current_user.get("role") or current_user.get("token_role") or "").lower()
    coop_id = _enforce_coop_access(current_user, cooperative_id)

    csv_content = generate_analytics_csv(
        export_type=type,
        cooperative_id=coop_id,
        current_role=user_role
    )

    filename = f"coop_analytics_{type}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
