# DSS-1.0 — Campus Energy Decision Support System
## AI Synergy Hackathon 2026 — Case 05: The 4 PM Spike

An **offline-first**, **deterministic**, **advisory-only** Human-AI Decision Support System that helps university campus decision-makers, facilities managers, and master electricians understand, investigate, and manage electricity demand during the evening peak-demand window (**16:00 inclusive to 20:00 exclusive**).

---

## 1. Core Principles & Differentiation

1. **Advisory-Only Safety Guarantee**: The system never triggers automatic equipment control or automated load shedding. It is an advisory decision support platform with human-in-the-loop review authority.
2. **Deterministic Core Decision Engine**: Evaluates telemetry through auditable, deterministic rules (`DSS-CORE-V1.0`). Same inputs always yield the same decision.
3. **16:00–20:00 Primary Demand Window**: Analyzes fifteen-minute intervals (:00, :15, :30, :45). The reading starting at 20:00 is strictly excluded (16 intervals per day).
4. **90% Completeness Gate**: Completeness is measured against expected scheduled intervals, not merely received records. Missing intervals are **never zero-filled**.
5. **Meter Boundary & Solar Truth**: Correctly differentiates `GROSS`, `NET`, `UNDECLARED`, and `CONFLICTING` boundaries. Gross demand is only reconstructed from net power when meter convention and solar alignment are verified.
6. **E0–E3 Evidence Assessment Engine**: Transparent evidentiary grading decoupled from urgency/severity. Human approval never automatically inflates evidence grades.
7. **Severity Scale**: Evaluates operational urgency (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFORMATIONAL`) based on documented engineering thresholds.
8. **Universal Decision Explanation System (13-Point Panel)**: Every metric, badge, finding, and recommendation features a "Why this result?" trigger that opens a 13-point structured panel without leaving context.
9. **Protected Facility Shield**: Protects mission-critical assets (e.g. Supercomputing Data Center, BSL-3 Bio Labs). Management overrides cannot bypass mandatory safety constraints.
10. **Offline-First & Governance**: Local processing, local SQLite database, local ML training/inference, with immutable append-only audit logging.

---

## 2. Quick Start & Demonstration

### Prerequisites
- Python 3.10+ (Tested on Python 3.14.0)
- Dependencies installed via `requirements.txt`:
  ```bash
  pip install -r requirements.txt
  ```

### Launching the Application
Run the operational server:
```bash
python run.py
```

The system will start on `http://127.0.0.1:8000/`.

### Portal Entry Points
| Interface | Route | Purpose |
|---|---|---|
| **Public Landing Page** | `http://localhost:8000/` | System overview, advisory positioning, role portal links |
| **Electrician Login** | `http://localhost:8000/login/electrician` | Ground-level technical inspection & feedback |
| **Management Login** | `http://localhost:8000/login/management` | Campus-wide analytics, review queue, overrides, audit |
| **Interactive API Docs** | `http://localhost:8000/docs` | OpenAPI / Swagger specification |

---

## 3. Seed Credentials & User Personas

| Username | Password | Role | Assigned Facilities / Scope |
|---|---|---|---|
| `electrician1` | `sparky2026!` | `ELECTRICIAN` | Engineering Complex, Humanities Hall, North Campus Dorm |
| `electrician2` | `current2026!` | `ELECTRICIAN` | Science Labs, Central Library, Athletics Center |
| `manager1` | `director2026!` | `MANAGEMENT` | Campus-Wide Director of Energy Operations |
| `admin1` | `admin2026!` | `ADMIN` | Campus Infrastructure System Administrator |

---

## 4. Key Workflows & Features

### A. Electrician Workflow (`/electrician`)
- **12 Dedicated Sections**: My Overview, My Assigned Buildings, My Assigned Tasks, Meter Readings, Solar & Meter Boundaries, Data Quality Issues, AI/DSS Findings, Decision Explanations, Submit Feedback, Feedback History, Notifications, Profile.
- **Field Feedback**: Electricians report physical observations under categories (`METER_CONFIGURATION`, `METER_BOUNDARY`, `SOLAR_MISMATCH`, etc.) without altering official DSS history.
- **Task Progression**: Update task status from `ASSIGNED` &rarr; `IN_PROGRESS` &rarr; `SUBMITTED_FOR_REVIEW` &rarr; `COMPLETED`.

### B. Managing Team Workflow (`/management`)
- **19 Dedicated Sections**: Campus Overview, Peak Demand Analysis, Building Explorer, Meter & Solar Analysis, Data Quality, Evidence Assessment, AI/DSS Recommendations, Pending Reviews, Electrician Feedback, Investigation Management, Human-AI Decision Comparison, Decision Override Center, Safety & Protected Buildings, Decision History, Audit Logs, Dataset Management, Model Management, Reports & Exports, Settings.
- **Decision Review**: Accept recommendations, or Reject/Modify with mandatory engineering justification.
- **Permitted Override**: Record management overrides with justification while strictly preserving original DSS snapshots.
- **Task Dispatch**: Assign field tasks to electricians with priority and safety instructions.

### C. Dataset Management (User's Own Dataset)
- **Import Formats**: CSV, XLSX, JSON.
- **Preview & Mapping**: Previews column names, sample rows, auto-detects canonical mapping (`timestamp`, `power_kw`, `energy_kwh`, `meter_code`, `building_code`).
- **Data Integrity**: Detects duplicates, flags missing intervals, never zero-fills, creates versioned dataset records.
- **Export Formats**: CSV, JSON, XLSX, and complete **ZIP bundle** containing data, manifest, and validation report.

### D. Offline Machine Learning & Governance
- **Data Suitability Gate**: Checks sample size, date span, and completeness. Rejects training if dataset is insufficient.
- **Time-Aware Split**: Chronological 80/20 train/test split (no future lookahead or random split data leakage).
- **Evaluation**: Evaluates candidate Ridge/RandomForest vs. Baseline Moving Persistence (MAE, RMSE, MAPE).
- **Governance**: Predictions are strictly labeled as estimates; cannot overwrite meter telemetry or bypass deterministic DSS decisions.

---

## 5. Decision Codes & Rules Reference

| Decision Code | Trigger Condition | Recommended Action |
|---|---|---|
| `RESOLVE_BOUNDARY` | Meter boundary is `UNDECLARED` or `CONFLICTING` | Single-line diagram & physical switchgear nameplate audit |
| `AUDIT_REGISTER` | Negative power readings on gross utility feed | CT polarity and meter register multiplier verification |
| `RECOMMEND_SUBMETERING` | 16:00-20:00 demand spike &ge; 20% on unmetered main feed | Install branch submetering on HVAC chillers / lab loads |
| `NO_ACTION` | Demand strictly matches historical baseline (<10% deviation) | Maintain routine telemetry surveillance |
| `INSUFFICIENT_DATA` | Demand window completeness < 90% in 16:00-20:00 | Recover logger buffer packets to reach 90% threshold |

---

## 6. Automated Test Suite Results

The entire acceptance suite passes cleanly with zero errors:

```bash
python -m pytest -v
```

```text
============================= test session starts =============================
platform win32 -- Python 3.14.0, pytest-9.2.0, pluggy-1.7.0
rootdir: C:\Users\Divys\OneDrive\Desktop\4PM Spike

tests/test_api.py::test_public_routes PASSED                             [  7%]
tests/test_api.py::test_authentication_workflows PASSED                  [ 14%]
tests/test_api.py::test_role_based_access_control PASSED                 [ 21%]
tests/test_api.py::test_electrician_jurisdiction_and_feedback PASSED     [ 28%]
tests/test_api.py::test_human_ai_review_and_override_safety PASSED       [ 35%]
tests/test_api.py::test_13_point_explanation_endpoint PASSED             [ 42%]
tests/test_dss.py::test_demand_window_and_intervals PASSED               [ 50%]
tests/test_dss.py::test_90_percent_completeness_calculation PASSED       [ 57%]
tests/test_dss.py::test_validation_detects_negative_gross_and_duplicates PASSED [ 64%]
tests/test_dss.py::test_boundary_and_solar_handling PASSED               [ 71%]
tests/test_dss.py::test_evidence_grades_deterministic PASSED             [ 78%]
tests/test_dss.py::test_protected_facility_severity_rules PASSED         [ 85%]
tests/test_dss.py::test_dss_pipeline_all_decision_codes PASSED           [ 92%]
tests/test_dss.py::test_ml_suitability_and_offline_training PASSED       [100%]

======================= 14 passed in 7.77s ========================
```

#   4 P M - S p i k e  
 