import os
import io
import datetime
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base, get_db
from app.config import (
    PEAK_WINDOW_START_HOUR,
    PEAK_WINDOW_END_HOUR,
    COMPLETENESS_THRESHOLD,
    RULE_VERSION
)
from app.engines.completeness import generate_expected_peak_intervals, evaluate_completeness
from app.engines.validation import validate_meter_readings_dataset, validate_solar_readings_dataset
from app.engines.boundary_solar import analyze_meter_boundary_and_solar
from app.engines.demand import filter_peak_window_readings, compute_demand_metrics
from app.engines.evidence import evaluate_evidence_grade
from app.engines.severity import evaluate_severity
from app.engines.eligibility import evaluate_eligibility
from app.engines.dss_engine import run_dss_deterministic_pipeline
from app.ml.suitability import assess_ml_suitability
from app.ml.trainer import train_demand_forecast_model

# -------------------------------------------------------------
# 1. DATA QUALITY & INGESTION TESTS
# -------------------------------------------------------------

def test_demand_window_and_intervals():
    """Validates that the peak demand window is 16:00 to 20:00 exclusive at 15-min intervals (16 intervals)."""
    target_date = datetime.date(2026, 10, 30)
    intervals = generate_expected_peak_intervals(target_date)

    assert len(intervals) == 16, "Must produce exactly 16 quarter-hour intervals per day"
    assert intervals[0].hour == 16 and intervals[0].minute == 0, "Window starts at 16:00"
    assert intervals[-1].hour == 19 and intervals[-1].minute == 45, "Window ends at 19:45"
    assert all(i.hour < 20 for i in intervals), "20:00 must be strictly excluded"

def test_90_percent_completeness_calculation():
    """Ensures completeness is calculated against scheduled expectation, not received count."""
    target_dates = [datetime.date(2026, 10, 30)] # 16 expected
    # 15 valid readings = 15/16 = 93.75% -> complete
    valid_readings = [
        {"timestamp": datetime.datetime(2026, 10, 30, 16, m), "power_kw": 200.0, "is_valid": True}
        for m in [0, 15, 30, 45]
    ] + [
        {"timestamp": datetime.datetime(2026, 10, 30, 17, m), "power_kw": 210.0, "is_valid": True}
        for m in [0, 15, 30, 45]
    ] + [
        {"timestamp": datetime.datetime(2026, 10, 30, 18, m), "power_kw": 220.0, "is_valid": True}
        for m in [0, 15, 30, 45]
    ] + [
        {"timestamp": datetime.datetime(2026, 10, 30, 19, m), "power_kw": 200.0, "is_valid": True}
        for m in [0, 15, 30] # 3 out of 4 intervals in hour 19
    ]

    res = evaluate_completeness(valid_readings, target_dates)
    assert res["expected_count"] == 16
    assert res["valid_count"] == 15
    assert res["completeness_pct"] == 93.75
    assert res["is_complete"] is True
    assert len(res["missing_timestamps"]) == 1

    # 13 valid readings = 13/16 = 81.25% -> fails 90% threshold
    res_incomplete = evaluate_completeness(valid_readings[:13], target_dates)
    assert res_incomplete["completeness_pct"] == 81.25
    assert res_incomplete["is_complete"] is False

def test_validation_detects_negative_gross_and_duplicates():
    """Detects duplicate timestamps and flags negative readings on gross meters as critical."""
    readings = [
        {"timestamp": "2026-10-30T16:00:00", "power_kw": 100.0},
        {"timestamp": "2026-10-30T16:00:00", "power_kw": 100.0}, # Duplicate
        {"timestamp": "2026-10-30T16:15:00", "power_kw": -85.0},  # Negative on gross!
        {"timestamp": "2026-10-30T16:30:00", "power_kw": "BAD_VAL"} # Non-numeric
    ]

    cleaned, findings, summary = validate_meter_readings_dataset(
        readings=readings,
        boundary_type="GROSS",
        meter_code="MTR-TEST"
    )

    categories = [f["issue_category"] for f in findings]
    assert "DUPLICATE_TIMESTAMPS" in categories
    assert "NEGATIVE_VALUES" in categories
    assert "CORRUPT_VALUE" in categories

    neg_finding = next(f for f in findings if f["issue_category"] == "NEGATIVE_VALUES")
    assert neg_finding["severity"] == "CRITICAL"

# -------------------------------------------------------------
# 2. BOUNDARY & SOLAR ANALYSIS TESTS
# -------------------------------------------------------------

def test_boundary_and_solar_handling():
    """Validates GROSS, NET, UNDECLARED, CONFLICTING and solar reconstruction rules."""
    meter_readings = [
        {"timestamp": datetime.datetime(2026, 10, 30, 16, 0), "power_kw": 150.0, "is_valid": True},
        {"timestamp": datetime.datetime(2026, 10, 30, 16, 15), "power_kw": 160.0, "is_valid": True}
    ]
    solar_readings = [
        {"timestamp": datetime.datetime(2026, 10, 30, 16, 0), "generation_kw": 40.0, "is_valid": True},
        {"timestamp": datetime.datetime(2026, 10, 30, 16, 15), "generation_kw": 30.0, "is_valid": True}
    ]

    # GROSS: does not deduct solar
    res_gross = analyze_meter_boundary_and_solar("GROSS", meter_readings, solar_readings)
    assert res_gross["can_reconstruct_gross"] is True
    assert res_gross["reconstructed_readings"][0]["gross_demand_kw"] == 150.0

    # NET with aligned solar: reconstructs gross = 150 + 40 = 190 kW
    res_net = analyze_meter_boundary_and_solar("NET", meter_readings, solar_readings)
    assert res_net["can_reconstruct_gross"] is True
    assert res_net["reconstructed_readings"][0]["gross_demand_kw"] == 190.0

    # UNDECLARED: cannot reconstruct gross
    res_und = analyze_meter_boundary_and_solar("UNDECLARED", meter_readings, solar_readings)
    assert res_und["can_reconstruct_gross"] is False
    assert res_und["is_boundary_resolved"] is False

# -------------------------------------------------------------
# 3. EVIDENCE & SEVERITY TESTS
# -------------------------------------------------------------

def test_evidence_grades_deterministic():
    """Validates deterministic assignment of E0, E1, E2, E3 grades."""
    # E0: Incomplete
    e0_res = evaluate_evidence_grade(
        completeness_metrics={"completeness_pct": 75.0, "valid_count": 12, "expected_count": 16, "missing_count": 4},
        boundary_analysis={"boundary_type": "GROSS", "is_boundary_resolved": True},
        data_quality_findings=[]
    )
    assert e0_res["evidence_grade"] == "E0"
    assert "below mandatory 90% threshold" in e0_res["why_assigned"]

    # E2: Complete >=95% and resolved boundary
    e2_res = evaluate_evidence_grade(
        completeness_metrics={"completeness_pct": 100.0, "valid_count": 16, "expected_count": 16, "missing_count": 0},
        boundary_analysis={"boundary_type": "GROSS", "is_boundary_resolved": True, "has_solar": False},
        data_quality_findings=[]
    )
    assert e2_res["evidence_grade"] == "E2"

    # E3: Gold standard with physical audit and calibration cert
    e3_res = evaluate_evidence_grade(
        completeness_metrics={"completeness_pct": 100.0, "valid_count": 16, "expected_count": 16, "missing_count": 0},
        boundary_analysis={"boundary_type": "GROSS", "is_boundary_resolved": True, "has_solar": False},
        data_quality_findings=[],
        has_physical_inspection_on_record=True,
        has_calibration_cert_on_record=True
    )
    assert e3_res["evidence_grade"] == "E3"
    assert "Audited & Certified" in e3_res["meaning"]

def test_protected_facility_severity_rules():
    """Protected building experiencing demand surge triggers CRITICAL severity."""
    crit_res = evaluate_severity(
        building_is_protected=True,
        demand_metrics={"peak_demand_kw": 680.0, "spike_vs_baseline_pct": 28.5},
        boundary_analysis={"boundary_type": "GROSS"},
        completeness_metrics={"completeness_pct": 100.0}
    )
    assert crit_res["severity"] == "CRITICAL"
    assert "Protected facility" in crit_res["triggering_condition"]

# -------------------------------------------------------------
# 4. DETERMINISTIC DSS DECISION CODES
# -------------------------------------------------------------

def test_dss_pipeline_all_decision_codes():
    """Tests deterministic generation of all 5 mandatory decision codes."""
    target_dates = [datetime.date(2026, 10, 30)]

    # 1. INSUFFICIENT_DATA (completeness < 90%)
    res_insuf = run_dss_deterministic_pipeline(
        building_dict={"name": "Athletics Center", "code": "BLD-ATH", "is_protected": False},
        meter_dict={"meter_code": "MTR-ATH", "boundary_type": "GROSS", "status": "ACTIVE"},
        readings=[{"timestamp": "2026-10-30T16:00:00", "power_kw": 200.0}], # Only 1 reading out of 16
        solar_readings=[],
        target_dates=target_dates
    )
    assert res_insuf["decision_code"] == "INSUFFICIENT_DATA"

    # 2. RESOLVE_BOUNDARY (boundary UNDECLARED)
    full_readings = [
        {"timestamp": f"2026-10-30T{h:02d}:{m:02d}:00", "power_kw": 200.0}
        for h in range(16, 20) for m in [0, 15, 30, 45]
    ]
    res_bnd = run_dss_deterministic_pipeline(
        building_dict={"name": "Humanities Hall", "code": "BLD-HUM", "is_protected": False},
        meter_dict={"meter_code": "MTR-HUM", "boundary_type": "UNDECLARED", "status": "ACTIVE"},
        readings=full_readings,
        solar_readings=[],
        target_dates=target_dates
    )
    assert res_bnd["decision_code"] == "RESOLVE_BOUNDARY"

    # 3. AUDIT_REGISTER (negative reading on gross meter)
    neg_readings = full_readings.copy()
    neg_readings[2] = {"timestamp": "2026-10-30T16:30:00", "power_kw": -60.0}
    res_audit = run_dss_deterministic_pipeline(
        building_dict={"name": "North Dormitory", "code": "BLD-DORM", "is_protected": False},
        meter_dict={"meter_code": "MTR-DORM", "boundary_type": "GROSS", "status": "ACTIVE"},
        readings=neg_readings,
        solar_readings=[],
        target_dates=target_dates
    )
    assert res_audit["decision_code"] == "AUDIT_REGISTER"

    # 4. RECOMMEND_SUBMETERING (demand > 300 kW and spike > 20% on main feed)
    spike_readings = [
        {"timestamp": f"2026-10-30T{h:02d}:{m:02d}:00", "power_kw": 520.0}
        for h in range(16, 20) for m in [0, 15, 30, 45]
    ]
    res_sub = run_dss_deterministic_pipeline(
        building_dict={"name": "Engineering Complex", "code": "BLD-ENG", "is_protected": False},
        meter_dict={"meter_code": "MTR-ENG", "boundary_type": "GROSS", "status": "ACTIVE", "register_type": "MAIN_FEED"},
        readings=spike_readings,
        solar_readings=[],
        target_dates=target_dates,
        historical_baseline_kw=350.0
    )
    assert res_sub["decision_code"] == "RECOMMEND_SUBMETERING"

    # 5. NO_ACTION (within baseline envelope)
    normal_readings = [
        {"timestamp": f"2026-10-30T{h:02d}:{m:02d}:00", "power_kw": 355.0}
        for h in range(16, 20) for m in [0, 15, 30, 45]
    ]
    res_none = run_dss_deterministic_pipeline(
        building_dict={"name": "Quiet Hall", "code": "BLD-Q", "is_protected": False},
        meter_dict={"meter_code": "MTR-Q", "boundary_type": "GROSS", "status": "ACTIVE"},
        readings=normal_readings,
        solar_readings=[],
        target_dates=target_dates,
        historical_baseline_kw=350.0
    )
    assert res_none["decision_code"] == "NO_ACTION"

# -------------------------------------------------------------
# 5. MACHINE LEARNING SUITABILITY & TIME-AWARE TRAIN TESTS
# -------------------------------------------------------------

def test_ml_suitability_and_offline_training():
    """Validates ML data suitability check and time-aware evaluation."""
    # Test 1: Trivial dataset fails suitability
    few_readings = [{"timestamp": f"2026-10-30T16:{m:02d}:00", "power_kw": 200.0} for m in [0, 15, 30]]
    suit_fail = assess_ml_suitability(few_readings)
    assert suit_fail["is_suitable"] is False

    # Test 2: Sufficient multi-day interval series passes suitability
    multi_day_readings = []
    base_dt = datetime.datetime(2026, 10, 25, 0, 0)
    for i in range(150):
        dt = base_dt + datetime.timedelta(minutes=15 * i)
        power = 300.0 + (dt.hour * 10.0) + (i % 20)
        multi_day_readings.append({"timestamp": dt.isoformat(), "power_kw": power})

    suit_pass = assess_ml_suitability(multi_day_readings)
    assert suit_pass["is_suitable"] is True

    # Test 3: Train model with time-aware split and evaluate MAE
    train_res = train_demand_forecast_model(multi_day_readings, model_type="RIDGE_REGRESSION")
    assert "metrics" in train_res
    assert "mae" in train_res["metrics"]
    assert train_res["metrics"]["mae"] >= 0.0
    assert "baseline_metrics" in train_res
    assert train_res["train_samples"] > 0
    assert train_res["test_samples"] > 0

