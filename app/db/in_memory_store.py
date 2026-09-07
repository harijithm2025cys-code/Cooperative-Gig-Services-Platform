"""
Shared In-Memory Data Store & Seed Registry for Cooperative Gig Services Platform.
Ensures deterministic testing, zero-downtime offline fallbacks, and multi-role consistency.
"""
import uuid
from typing import Dict, Any, List
from datetime import datetime, timezone

# -------------------------------------------------------------------------
# Seed Cooperatives
# -------------------------------------------------------------------------
_COOPERATIVES_BY_ID: Dict[str, Dict[str, Any]] = {
    "coop_north_01": {
        "id": "coop_north_01",
        "name": "North Chennai Labour Contract Cooperative Society",
        "district": "Chennai North",
        "state": "Tamil Nadu",
        "address": "42 Rajaji Salai, Chennai",
        "registration_number": "TN-LCS-2021-0842",
        "contact_email": "north_society@tnlabourcoop.org",
        "contact_phone": "+91 44 2534 8890",
        "verified": True,
        "created_at": "2024-01-15T09:00:00Z"
    },
    "coop_south_02": {
        "id": "coop_south_02",
        "name": "South Chennai Skilled Workers Cooperative Union",
        "district": "Chennai South",
        "state": "Tamil Nadu",
        "address": "15 Sardar Patel Road, Adyar, Chennai",
        "registration_number": "TN-LCS-2022-1190",
        "contact_email": "south_union@tnlabourcoop.org",
        "contact_phone": "+91 44 2441 5566",
        "verified": True,
        "created_at": "2024-02-10T10:30:00Z"
    },
    "coop_coimbatore_03": {
        "id": "coop_coimbatore_03",
        "name": "Coimbatore Industrial Labour & Artisan Cooperative Society",
        "district": "Coimbatore",
        "state": "Tamil Nadu",
        "address": "88 Avinashi Road, Peelamedu, Coimbatore",
        "registration_number": "TN-LCS-2020-0412",
        "contact_email": "cbe_artisans@tnlabourcoop.org",
        "contact_phone": "+91 422 257 3344",
        "verified": True,
        "created_at": "2024-03-01T11:00:00Z"
    }
}

# -------------------------------------------------------------------------
# Seed Users (5-Role System)
# -------------------------------------------------------------------------
_USERS_BY_ID: Dict[str, Dict[str, Any]] = {
    "usr_super_admin_01": {
        "id": "usr_super_admin_01",
        "name": "Platform Super Administrator",
        "email": "superadmin@coopservices.gov.in",
        "phone": "+91 98400 00001",
        "role": "super_admin",
        "cooperative_id": None,
        "created_at": "2024-01-01T00:00:00Z"
    },
    "usr_head_north_01": {
        "id": "usr_head_north_01",
        "name": "Sundaramoorthy (Association Head)",
        "email": "head.north@tnlabourcoop.org",
        "phone": "+91 98400 11001",
        "role": "cooperative_association_head",
        "cooperative_id": "coop_north_01",
        "created_at": "2024-01-15T09:30:00Z"
    },
    "usr_head_south_02": {
        "id": "usr_head_south_02",
        "name": "Venkatesan (South Head)",
        "email": "head.south@tnlabourcoop.org",
        "phone": "+91 98400 22002",
        "role": "cooperative_association_head",
        "cooperative_id": "coop_south_02",
        "created_at": "2024-02-10T11:00:00Z"
    },
    "usr_wrk_1": {
        "id": "usr_wrk_1",
        "name": "Kumar Specialist",
        "email": "kumar.plumber@tnlabourcoop.org",
        "phone": "+91 98450 11223",
        "role": "cooperative_worker",
        "cooperative_id": "coop_north_01",
        "created_at": "2024-01-20T10:00:00Z"
    },
    "usr_wrk_2": {
        "id": "usr_wrk_2",
        "name": "Dhanabalan R",
        "email": "dhanabalan.elec@tnlabourcoop.org",
        "phone": "+91 98450 22334",
        "role": "cooperative_worker",
        "cooperative_id": "coop_north_01",
        "created_at": "2024-01-22T11:00:00Z"
    },
    "usr_wrk_3": {
        "id": "usr_wrk_3",
        "name": "Murugan Carpenter",
        "email": "murugan.carpentry@tnlabourcoop.org",
        "phone": "+91 98450 33445",
        "role": "cooperative_worker",
        "cooperative_id": "coop_south_02",
        "created_at": "2024-02-15T12:00:00Z"
    },
    "usr_wrk_ind_1": {
        "id": "usr_wrk_ind_1",
        "name": "Karthik Independent Pro",
        "email": "karthik.freelance@gmail.com",
        "phone": "+91 98450 99887",
        "role": "independent_worker",
        "cooperative_id": None,
        "created_at": "2024-02-20T14:00:00Z"
    },
    "usr_cust_01": {
        "id": "usr_cust_01",
        "name": "Ananya Sharma",
        "email": "ananya.sharma@example.com",
        "phone": "+91 98765 43210",
        "role": "customer",
        "cooperative_id": None,
        "created_at": "2024-03-01T08:00:00Z"
    },
    "usr_cust_02": {
        "id": "usr_cust_02",
        "name": "Ramesh Krishnan",
        "email": "ramesh.krishnan@example.com",
        "phone": "+91 98765 88990",
        "role": "customer",
        "cooperative_id": None,
        "created_at": "2024-03-05T09:00:00Z"
    }
}

# -------------------------------------------------------------------------
# Seed Workers
# -------------------------------------------------------------------------
_WORKERS_BY_ID: Dict[str, Dict[str, Any]] = {
    "wrk_1": {
        "id": "wrk_1",
        "user_id": "usr_wrk_1",
        "name": "Kumar Specialist",
        "phone": "+91 98450 11223",
        "email": "kumar.plumber@tnlabourcoop.org",
        "skill": "Plumbing",
        "worker_type": "cooperative",
        "cooperative_id": "coop_north_01",
        "cooperative_name": "North Chennai Labour Contract Cooperative Society",
        "is_available": True,
        "availability_status": "available",
        "active": True,
        "verified_status": True,
        "is_pre_verified_by_association": True,
        "rating": 4.9,
        "hourly_rate": 350.0,
        "monthly_jobs": 8,
        "fairness_score": 22.5,
        "latitude": 13.0827,
        "longitude": 80.2707,
        "created_at": "2024-01-20T10:00:00Z"
    },
    "wrk_2": {
        "id": "wrk_2",
        "user_id": "usr_wrk_2",
        "name": "Dhanabalan R",
        "phone": "+91 98450 22334",
        "email": "dhanabalan.elec@tnlabourcoop.org",
        "skill": "Electrical",
        "worker_type": "cooperative",
        "cooperative_id": "coop_north_01",
        "cooperative_name": "North Chennai Labour Contract Cooperative Society",
        "is_available": True,
        "availability_status": "available",
        "active": True,
        "verified_status": True,
        "is_pre_verified_by_association": True,
        "rating": 4.8,
        "hourly_rate": 380.0,
        "monthly_jobs": 5,
        "fairness_score": 25.0,
        "latitude": 13.0900,
        "longitude": 80.2800,
        "created_at": "2024-01-22T11:00:00Z"
    },
    "wrk_3": {
        "id": "wrk_3",
        "user_id": "usr_wrk_3",
        "name": "Murugan Carpenter",
        "phone": "+91 98450 33445",
        "email": "murugan.carpentry@tnlabourcoop.org",
        "skill": "Carpentry",
        "worker_type": "cooperative",
        "cooperative_id": "coop_south_02",
        "cooperative_name": "South Chennai Skilled Workers Cooperative Union",
        "is_available": False,
        "availability_status": "working",
        "active": True,
        "verified_status": True,
        "is_pre_verified_by_association": True,
        "rating": 4.7,
        "hourly_rate": 400.0,
        "monthly_jobs": 12,
        "fairness_score": 15.0,
        "latitude": 13.0012,
        "longitude": 80.2565,
        "created_at": "2024-02-15T12:00:00Z"
    },
    "wrk_ind_1": {
        "id": "wrk_ind_1",
        "user_id": "usr_wrk_ind_1",
        "name": "Karthik Independent Pro",
        "phone": "+91 98450 99887",
        "email": "karthik.freelance@gmail.com",
        "skill": "AC Repair",
        "worker_type": "independent",
        "cooperative_id": None,
        "cooperative_name": "Independent Contractor",
        "is_available": True,
        "availability_status": "available",
        "active": True,
        "verified_status": True,
        "is_pre_verified_by_association": False,
        "rating": 4.6,
        "hourly_rate": 450.0,
        "monthly_jobs": 6,
        "fairness_score": 18.0,
        "latitude": 13.0500,
        "longitude": 80.2400,
        "created_at": "2024-02-20T14:00:00Z"
    }
}

# -------------------------------------------------------------------------
# Seed Services Catalog
# -------------------------------------------------------------------------
_SERVICES_BY_ID: Dict[str, Dict[str, Any]] = {
    "srv_plumbing_01": {
        "id": "srv_plumbing_01",
        "name": "Plumbing & Pipe Repair",
        "category": "Plumbing",
        "description": "Certified cooperative plumbers for leakage repair, pipe replacement, and fixtures.",
        "base_price": 350.0,
        "unit": "job",
        "cooperative_id": "coop_north_01",
        "is_active": True,
        "created_at": "2024-01-16T10:00:00Z"
    },
    "srv_electrical_02": {
        "id": "srv_electrical_02",
        "name": "Electrical & Circuit Inspection",
        "category": "Electrical",
        "description": "Standardized safety certified electrical diagnostic, switchboard, and wiring repairs.",
        "base_price": 380.0,
        "unit": "job",
        "cooperative_id": "coop_north_01",
        "is_active": True,
        "created_at": "2024-01-16T10:30:00Z"
    },
    "srv_carpentry_03": {
        "id": "srv_carpentry_03",
        "name": "Carpentry & Furniture Assembly",
        "category": "Carpentry",
        "description": "Furniture repairs, door hinges, shelving, and wood polishing.",
        "base_price": 400.0,
        "unit": "job",
        "cooperative_id": "coop_south_02",
        "is_active": True,
        "created_at": "2024-02-12T11:00:00Z"
    },
    "srv_ac_04": {
        "id": "srv_ac_04",
        "name": "AC Service & Deep Gas Refill",
        "category": "Appliances",
        "description": "Split and window air conditioner servicing, filter cleaning, and refrigerant check.",
        "base_price": 450.0,
        "unit": "job",
        "cooperative_id": None,  # Platform general / independent
        "is_active": True,
        "created_at": "2024-02-15T09:00:00Z"
    }
}

# -------------------------------------------------------------------------
# Administrative Audit Logs
# -------------------------------------------------------------------------
_ADMIN_AUDIT_LOGS: List[Dict[str, Any]] = [
    {
        "id": "log_init_01",
        "actor_id": "usr_super_admin_01",
        "actor_role": "super_admin",
        "action": "SYSTEM_INITIALIZED",
        "target_type": "platform",
        "target_id": "tn_federation_root",
        "details": "Federation governance platform v6.0 management layer activated.",
        "created_at": "2024-01-01T00:00:00Z"
    }
]

def record_admin_audit(
    actor_id: str,
    actor_role: str,
    action: str,
    target_type: str,
    target_id: str,
    details: str
) -> Dict[str, Any]:
    entry = {
        "id": f"log_{uuid.uuid4().hex[:8]}",
        "actor_id": actor_id,
        "actor_role": actor_role,
        "action": action,
        "target_type": target_type,
        "target_id": target_id,
        "details": details,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    _ADMIN_AUDIT_LOGS.insert(0, entry)
    return entry

# -------------------------------------------------------------------------
# Shared In-Memory Complaints / Disputes Registry
# -------------------------------------------------------------------------
_COMPLAINTS_BY_ID: Dict[str, Dict[str, Any]] = {}
