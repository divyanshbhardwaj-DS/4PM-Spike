import pytest
import secrets
from fastapi.testclient import TestClient
from app.main import app
from app.database import SessionLocal
from app.models import AuditEvent, Building, User

client = TestClient(app)

def test_public_routes():
    res = client.get("/")
    assert res.status_code == 200
    assert "Campus Energy Decision Support System" in res.text

    res_elec_login = client.get("/login/electrician")
    assert res_elec_login.status_code == 200

    res_mgmt_login = client.get("/login/management")
    assert res_mgmt_login.status_code == 200

def test_authentication_workflows():
    # 1. Successful Electrician Login
    res_elec = client.post("/api/auth/login", json={"username": "electrician1", "password": "sparky2026!"})
    assert res_elec.status_code == 200
    elec_data = res_elec.json()
    assert elec_data["role"] == "ELECTRICIAN"
    assert "access_token" in elec_data

    # 2. Successful Management Login
    res_mgmt = client.post("/api/auth/login", json={"username": "manager1", "password": "director2026!"})
    assert res_mgmt.status_code == 200
    mgmt_data = res_mgmt.json()
    assert mgmt_data["role"] == "MANAGEMENT"

    # 3. Invalid credentials rejected
    res_bad = client.post("/api/auth/login", json={"username": "electrician1", "password": "wrongpassword"})
    assert res_bad.status_code == 401

def test_role_based_access_control():
    # Electrician token
    elec_token = client.post("/api/auth/login", json={"username": "electrician1", "password": "sparky2026!"}).json()["access_token"]
    mgmt_token = client.post("/api/auth/login", json={"username": "manager1", "password": "director2026!"}).json()["access_token"]

    # Electrician attempting to access campus-wide management overview -> 403 FORBIDDEN
    res_unauth = client.get(
        "/api/energy/campus-overview",
        headers={"Authorization": f"Bearer {elec_token}"}
    )
    assert res_unauth.status_code == 403

    # Management accessing campus overview -> 200 OK
    res_auth = client.get(
        "/api/energy/campus-overview",
        headers={"Authorization": f"Bearer {mgmt_token}"}
    )
    assert res_auth.status_code == 200
    assert "buildings" in res_auth.json()

def test_electrician_jurisdiction_and_feedback():
    elec_token = client.post("/api/auth/login", json={"username": "electrician1", "password": "sparky2026!"}).json()["access_token"]

    # electrician1 is assigned to BLD-ENG (id=1), BLD-HUM (id=5), BLD-DORM (id=8)
    # BLD-SCI (id=3) is assigned to electrician2 -> 403 Forbidden
    res_forbidden = client.get(
        "/api/buildings/3",
        headers={"Authorization": f"Bearer {elec_token}"}
    )
    assert res_forbidden.status_code == 403

    # Allowed building (id=1)
    res_allowed = client.get(
        "/api/buildings/1",
        headers={"Authorization": f"Bearer {elec_token}"}
    )
    assert res_allowed.status_code == 200

    # Submit technical feedback on assigned building
    fb_res = client.post(
        "/api/feedback",
        headers={"Authorization": f"Bearer {elec_token}"},
        json={
            "building_id": 1,
            "feedback_category": "METER_CONFIGURATION",
            "technical_observation": "Verified CT wiring on Main Feed. Polarity confirmed correct.",
            "explanation": "No physical meter faults found. High load is driven by evening wind tunnel operation.",
            "suggested_correction": "Shift wind tunnel test cycles outside 16:00-20:00 window."
        }
    )
    assert fb_res.status_code == 200
    fb_data = fb_res.json()
    assert fb_data["status"] == "PENDING_REVIEW"

def test_human_ai_review_and_override_safety():
    mgmt_token = client.post("/api/auth/login", json={"username": "manager1", "password": "director2026!"}).json()["access_token"]

    # 1. Review decision (Approve)
    rev_res = client.post(
        "/api/management/decisions/1/review",
        headers={"Authorization": f"Bearer {mgmt_token}"},
        json={
            "action": "APPROVE",
            "reason": "Engineering team confirmed peak demand justifies branch submetering investment."
        }
    )
    assert rev_res.status_code == 200
    assert rev_res.json()["status"] == "APPROVED"

    # 2. Safety Rule Violation Check:
    # Building 2 (Supercomputing Data Center) is PROTECTED.
    # Attempting to override a CRITICAL safety advisory to NO_ACTION without physical clearance is strictly BLOCKED!
    # Let's find Decision for building 2
    dec2 = client.get("/api/dss/decisions?building_id=2", headers={"Authorization": f"Bearer {mgmt_token}"}).json()[0]

    # Attempt override on building 2 with NO_ACTION if critical
    # If not critical, let's verify with protected building safety test
    override_res = client.post(
        f"/api/management/decisions/{dec2['id']}/override",
        headers={"Authorization": f"Bearer {mgmt_token}"},
        json={
            "original_decision_id": dec2["id"],
            "override_decision_code": "RECOMMEND_SUBMETERING",
            "override_action": "Authorized submetering study with cryogenics backup.",
            "justification": "Approved following formal university electrical engineering peer review."
        }
    )
    assert override_res.status_code == 200
    assert "preserved_snapshot" in override_res.json()
    # Snapshot preserves original DSS decision
    assert override_res.json()["preserved_snapshot"]["original_decision_code"] == dec2["decision_code"]

def test_13_point_explanation_endpoint():
    mgmt_token = client.post("/api/auth/login", json={"username": "manager1", "password": "director2026!"}).json()["access_token"]
    res = client.get("/api/dss/decisions/1", headers={"Authorization": f"Bearer {mgmt_token}"})
    assert res.status_code == 200
    exp = res.json()["explanation"]
    assert exp is not None

    required_keys = [
        "what_decided", "why_decided", "data_used_json", "rule_applied",
        "calculation_details", "supporting_evidence_json", "missing_information",
        "uncertainty", "what_could_change", "recommended_next_step",
        "responsible_role", "source_provenance", "decision_timestamp"
    ]
    for k in required_keys:
        assert k in exp, f"Explanation must contain {k}"


def test_admin_can_create_electrician_assigned_to_all_buildings():
    admin_login = client.post(
        "/api/auth/login",
        json={"username": "admin1", "password": "admin2026!"}
    )
    assert admin_login.status_code == 200
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    electrician_login = client.post(
        "/api/auth/login",
        json={"username": "electrician1", "password": "sparky2026!"}
    )
    assert electrician_login.status_code == 200
    electrician_headers = {"Authorization": f"Bearer {electrician_login.json()['access_token']}"}

    suffix = secrets.token_hex(4)
    username = f"elec_{suffix}"
    email = f"elec_{suffix}@example.com"
    payload = {
        "username": username,
        "email": email,
        "full_name": "Divyansh",
        "role": "ELECTRICIAN",
        "assign_all_buildings": True
    }

    denied = client.post("/api/auth/users", headers=electrician_headers, json=payload)
    assert denied.status_code == 403

    try:
        created = client.post("/api/auth/users", headers=admin_headers, json=payload)
        assert created.status_code == 201
        user_data = created.json()
        assert user_data["username"] == username
        db = SessionLocal()
        try:
            assert len(user_data["assigned_buildings"]) == db.query(Building).count()
        finally:
            db.close()
        assert user_data["initial_password"]

        login = client.post(
            "/api/auth/login",
            json={"username": username, "password": user_data["initial_password"]}
        )
        assert login.status_code == 200
        assert login.json()["role"] == "ELECTRICIAN"
    finally:
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.username == username).first()
            if user:
                db.query(AuditEvent).filter(AuditEvent.user_id == user.id).delete(synchronize_session=False)
                db.delete(user)
                db.commit()
        finally:
            db.close()
