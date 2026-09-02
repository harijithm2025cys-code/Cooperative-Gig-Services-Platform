#!/usr/bin/env python3
"""
Seed script for the home services database.
Inserts cooperatives, services, worker/household users and their profiles.
"""

import os
import random
import sys
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set in .env")
    sys.exit(1)

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ----------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------
BASE_LAT = 13.0827   # Chennai latitude
BASE_LON = 80.2707   # Chennai longitude
RADIUS_DEG = 0.09    # ~10 km (1 deg lat ≈ 111 km)

# ----------------------------------------------------------------------
# Helper functions
# ----------------------------------------------------------------------
def random_coord():
    """Return (lat, lon) within ~10 km of Chennai."""
    lat = BASE_LAT + random.uniform(-RADIUS_DEG, RADIUS_DEG)
    lon = BASE_LON + random.uniform(-RADIUS_DEG, RADIUS_DEG)
    return round(lat, 6), round(lon, 6)

def safe_insert(table: str, data: dict, context: str):
    """Insert one row and return the inserted record (with id)."""
    try:
        result = supabase.table(table).insert(data).execute()
        if not result.data:
            raise Exception(f"No data returned from insert into {table}")
        return result.data[0]
    except Exception as e:
        print(f"❌ ERROR during insert into {table}: {context}")
        print(f"   Details: {e}")
        sys.exit(1)

def safe_insert_many(table: str, data_list: list, context: str):
    """Insert multiple rows and return the list of inserted records."""
    try:
        result = supabase.table(table).insert(data_list).execute()
        if not result.data:
            raise Exception(f"No data returned from insert into {table}")
        return result.data
    except Exception as e:
        print(f"❌ ERROR during batch insert into {table}: {context}")
        print(f"   Details: {e}")
        sys.exit(1)

# ----------------------------------------------------------------------
# Seed data definitions
# ----------------------------------------------------------------------
cooperatives_data = [
    {"name": "Chennai South Cooperative", "district": "Chennai", "state": "Tamil Nadu"},
    {"name": "Chennai North Cooperative", "district": "Chennai", "state": "Tamil Nadu"},
]

services_data = [
    {"name": "electrician", "category": "Home Repair"},
    {"name": "plumber", "category": "Home Repair"},
    {"name": "caregiver", "category": "Care Services"},
    {"name": "driver", "category": "Transport"},
    {"name": "cleaner", "category": "Home Services"},
]

# 12 workers with realistic names, skills and cooperative assignment (0 or 1)
workers_info = [
    # Electricians (3)
    {"name": "Rajesh Kumar", "phone": "9840123450", "email": "rajesh.kumar@example.com", "skill": "electrician", "coop_idx": 0},
    {"name": "Suresh Babu", "phone": "9840123451", "email": "suresh.babu@example.com", "skill": "electrician", "coop_idx": 1},
    {"name": "Mani Vannan", "phone": "9840123452", "email": "mani.vannan@example.com", "skill": "electrician", "coop_idx": 0},
    # Plumbers (3)
    {"name": "Karthik Raja", "phone": "9840123453", "email": "karthik.raja@example.com", "skill": "plumber", "coop_idx": 1},
    {"name": "Prakash Raj", "phone": "9840123454", "email": "prakash.raj@example.com", "skill": "plumber", "coop_idx": 0},
    {"name": "Vinoth Kumar", "phone": "9840123455", "email": "vinoth.kumar@example.com", "skill": "plumber", "coop_idx": 1},
    # Caregivers (2)
    {"name": "Lakshmi Narayanan", "phone": "9840123456", "email": "lakshmi.narayanan@example.com", "skill": "caregiver", "coop_idx": 0},
    {"name": "Meenakshi Sundaram", "phone": "9840123457", "email": "meenakshi.sundaram@example.com", "skill": "caregiver", "coop_idx": 1},
    # Drivers (2)
    {"name": "Ganesh Moorthy", "phone": "9840123458", "email": "ganesh.moorthy@example.com", "skill": "driver", "coop_idx": 0},
    {"name": "Selvamani", "phone": "9840123459", "email": "selvamani@example.com", "skill": "driver", "coop_idx": 1},
    # Cleaners (2)
    {"name": "Murugan", "phone": "9840123460", "email": "murugan@example.com", "skill": "cleaner", "coop_idx": 0},
    {"name": "Ravi Shankar", "phone": "9840123461", "email": "ravi.shankar@example.com", "skill": "cleaner", "coop_idx": 1},
]

households_info = [
    {"name": "Anitha Ramesh", "phone": "9840123470", "email": "anitha.ramesh@example.com", "address": "12, Gandhi Street, T. Nagar, Chennai"},
    {"name": "Kavitha Srinivasan", "phone": "9840123471", "email": "kavitha.srinivasan@example.com", "address": "45, Anna Salai, Chennai"},
    {"name": "Deepak Kumar", "phone": "9840123472", "email": "deepak.kumar@example.com", "address": "78, Velachery Main Road, Chennai"},
    {"name": "Priya Raman", "phone": "9840123473", "email": "priya.raman@example.com", "address": "23, Mylapore, Chennai"},
]

# ----------------------------------------------------------------------
# Counters for summary
# ----------------------------------------------------------------------
counts = {
    "cooperatives": 0,
    "services": 0,
    "users": 0,
    "workers": 0,
    "households": 0,
}

# ----------------------------------------------------------------------
# Seeding process
# ----------------------------------------------------------------------
print("\n🚀 Starting database seed...\n")

# 1. Insert cooperatives
print("Inserting cooperatives...")
coop_records = safe_insert_many("cooperatives", cooperatives_data, "cooperatives")
counts["cooperatives"] = len(coop_records)
print(f"✅ Inserted {counts['cooperatives']} cooperatives\n")

# 2. Insert services
print("Inserting services...")
service_records = safe_insert_many("services", services_data, "services")
counts["services"] = len(service_records)
print(f"✅ Inserted {counts['services']} services\n")

# 3. Insert worker users and profiles
print("Inserting worker users and profiles...")
for idx, w in enumerate(workers_info, start=1):
    # Create user
    user_data = {
        "name": w["name"],
        "phone": w["phone"],
        "email": w["email"],
        "role": "worker",
        "created_at": "now()",  # Supabase will use default if omitted, but we can set explicitly
    }
    user_record = safe_insert("users", user_data, f"worker user {w['name']}")
    counts["users"] += 1

    # Create worker profile
    lat, lon = random_coord()
    rating = round(random.uniform(3.5, 5.0), 1)
    worker_data = {
        "user_id": user_record["id"],
        "skill": w["skill"],
        "cooperative_id": coop_records[w["coop_idx"]]["id"],
        "latitude": lat,
        "longitude": lon,
        "rating": rating,
        "is_verified": True,
        "is_available": True,
    }
    safe_insert("workers", worker_data, f"worker profile for {w['name']}")
    counts["workers"] += 1
    print(f"  ✅ ({idx}/{len(workers_info)}) Created {w['name']} as {w['skill']}")

print(f"✅ Inserted {counts['workers']} worker profiles\n")

# 4. Insert household users and profiles
print("Inserting household users and profiles...")
for idx, h in enumerate(households_info, start=1):
    # Create user
    user_data = {
        "name": h["name"],
        "phone": h["phone"],
        "email": h["email"],
        "role": "household",
        "created_at": "now()",
    }
    user_record = safe_insert("users", user_data, f"household user {h['name']}")
    counts["users"] += 1

    # Create household profile
    lat, lon = random_coord()
    household_data = {
        "user_id": user_record["id"],
        "address": h["address"],
        "latitude": lat,
        "longitude": lon,
    }
    safe_insert("households", household_data, f"household profile for {h['name']}")
    counts["households"] += 1
    print(f"  ✅ ({idx}/{len(households_info)}) Created {h['name']}")

print(f"✅ Inserted {counts['households']} household profiles\n")

# ----------------------------------------------------------------------
# Final summary
# ----------------------------------------------------------------------
print("=" * 50)
print("🎉 Seed completed successfully!")
print("=" * 50)
print(f"Cooperatives : {counts['cooperatives']}")
print(f"Services     : {counts['services']}")
print(f"Users        : {counts['users']} (12 workers + 4 households)")
print(f"Workers      : {counts['workers']}")
print(f"Households   : {counts['households']}")
print("=" * 50)