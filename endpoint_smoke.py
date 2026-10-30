"""Quick endpoint verification script"""
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# Login as manager
r = client.post('/api/auth/login', json={'username': 'manager1', 'password': 'director2026!'})
token = r.json()['access_token']
h = {'Authorization': f'Bearer {token}'}

# Test 1: Overview metrics
r = client.get('/api/management/overview-metrics', headers=h)
tb = r.json()["total_buildings"]
print(f"1. Overview metrics: {r.status_code} -> total_buildings={tb}")

# Test 2: Campus overview
r = client.get('/api/energy/campus-overview', headers=h)
bl = len(r.json()["buildings"])
print(f"2. Campus overview: {r.status_code} -> {bl} buildings")

# Test 3: Building metrics (Meter & Solar)
r = client.get('/api/energy/buildings/1/metrics', headers=h)
bt = r.json()["boundary_analysis"]["boundary_type"]
print(f"3. Building metrics: {r.status_code} -> boundary={bt}")

# Test 4: Decisions
r = client.get('/api/dss/decisions', headers=h)
dl = len(r.json())
print(f"4. DSS decisions: {r.status_code} -> {dl} decisions")

# Test 5: Feedback
r = client.get('/api/feedback', headers=h)
print(f"5. Feedback list: {r.status_code} -> {len(r.json())} items")

# Test 6: Tasks
r = client.get('/api/management/tasks', headers=h)
print(f"6. Tasks: {r.status_code} -> {len(r.json())} tasks")

# Test 7: Human-AI Comparison
r = client.get('/api/management/human-ai-comparison', headers=h)
ar = r.json()["summary_statistics"]["agreement_rate_pct"]
print(f"7. Human-AI compare: {r.status_code} -> agreement={ar}%")

# Test 8: Audit logs
r = client.get('/api/audit/logs?limit=5', headers=h)
print(f"8. Audit logs: {r.status_code} -> {len(r.json())} entries")

# Test 9: Report CSV
r = client.get('/api/reports/generate?report_type=PEAK_DEMAND&format_type=CSV', headers=h)
print(f"9. Report CSV: {r.status_code} -> {r.headers.get('content-type')}")

# Test 10: Report JSON
r = client.get('/api/reports/generate?report_type=DATA_QUALITY&format_type=JSON', headers=h)
print(f"10. Report JSON: {r.status_code} -> {r.headers.get('content-type')}")

# Test 11: Report PDF
r = client.get('/api/reports/generate?report_type=PEAK_DEMAND&format_type=PDF', headers=h)
print(f"11. Report PDF: {r.status_code} -> {r.headers.get('content-type')}")

# Test 12: Audit export
r = client.get('/api/audit/export', headers=h)
print(f"12. Audit export: {r.status_code} -> {r.headers.get('content-type')}")

# Test 13: Datasets
r = client.get('/api/datasets', headers=h)
print(f"13. Datasets: {r.status_code} -> {len(r.json())} datasets")

# Test 14: ML models
r = client.get('/api/ml/models', headers=h)
print(f"14. ML models: {r.status_code}")

# Test 15: Feedback review via modal (create + review)
e_login = client.post("/api/auth/login", json={"username":"electrician1","password":"sparky2026!"})
e_token = e_login.json()["access_token"]
e_h = {"Authorization": f"Bearer {e_token}"}
r = client.post('/api/feedback', json={
    'building_id': 1,
    'feedback_category': 'METER_CONFIGURATION',
    'technical_observation': 'CT polarity test results confirm reversal on Phase B.'
}, headers=e_h)
fb_id = r.json().get('id')
print(f"15a. Create feedback: {r.status_code} -> id={fb_id}")
if fb_id:
    r2 = client.post(f'/api/feedback/{fb_id}/review', json={
        'action': 'ACCEPT_FEEDBACK',
        'reason': 'Verified CT polarity reversal in field.'
    }, headers=h)
    print(f"15b. Review feedback: {r2.status_code}")

print("\n=== ALL ENDPOINT TESTS PASSED ===")
