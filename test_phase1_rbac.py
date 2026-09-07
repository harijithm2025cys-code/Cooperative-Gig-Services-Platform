import asyncio
from app.models.auth import UserRegister, UserRoleType
from app.core.dependencies import require_role, require_association_access, ROLE_ALIASES

def test_user_roles():
    # Test valid 5 roles
    roles = ["customer", "independent_worker", "cooperative_association_head", "cooperative_worker", "super_admin"]
    for r in roles:
        reg = UserRegister(
            email=f"{r}@test.com",
            phone="9876543210",
            password="password123",
            role=r,
            name=f"Test {r}",
            skill="Electrician" if "worker" in r else None,
            worker_type="cooperative" if r == "cooperative_worker" else ("independent" if r == "independent_worker" else None)
        )
        assert reg.role == r
        print(f"[OK] Validated role: {r}")

def test_role_aliases_and_rbac():
    # Customer
    checker_customer = require_role(["customer"])
    user_hh = {"id": "1", "role": "household"}
    res = asyncio.run(checker_customer(user_hh))
    assert res == user_hh
    print("[OK] Passed customer / household alias test")

    # Co-op Worker
    checker_worker = require_role(["cooperative_worker"])
    user_cw = {"id": "2", "role": "cooperative_worker"}
    res2 = asyncio.run(checker_worker(user_cw))
    assert res2 == user_cw
    print("[OK] Passed cooperative_worker test")

    # Independent Worker
    checker_ind = require_role(["independent_worker"])
    user_ind = {"id": "3", "role": "independent_worker"}
    res3 = asyncio.run(checker_ind(user_ind))
    assert res3 == user_ind
    print("[OK] Passed independent_worker test")

    # Super Admin universal access
    user_super = {"id": "4", "role": "super_admin"}
    res4 = asyncio.run(checker_customer(user_super))
    assert res4 == user_super
    print("[OK] Passed super_admin universal access test")

def test_association_data_isolation():
    access_checker = require_association_access("coop_01")
    
    # Matching Association Head -> Allowed
    head_user = {"id": "h1", "role": "cooperative_association_head", "cooperative_id": "coop_01"}
    res = asyncio.run(access_checker("coop_01", head_user, None))
    assert res == head_user
    print("[OK] Passed Association Head own society access")

    # Mismatched Association Head -> Blocked
    diff_head = {"id": "h2", "role": "cooperative_association_head", "cooperative_id": "coop_02"}
    try:
        asyncio.run(access_checker("coop_01", diff_head, None))
        assert False, "Should have thrown 403"
    except Exception as e:
        assert "403" in str(e) or "Access denied" in str(e)
        print("[OK] Passed Association Head cross-society data isolation block")

    # Super Admin -> Allowed cross-society
    super_admin = {"id": "sa", "role": "super_admin"}
    res_sa = asyncio.run(access_checker("coop_01", super_admin, None))
    assert res_sa == super_admin
    print("[OK] Passed Super Admin cross-society federation access")

if __name__ == "__main__":
    print("--- RUNNING PHASE 1 BACKEND RBAC & 5-ROLE TESTS ---")
    test_user_roles()
    test_role_aliases_and_rbac()
    test_association_data_isolation()
    print("--- ALL PHASE 1 BACKEND TESTS PASSED SUCCESSFULLY! ---")
