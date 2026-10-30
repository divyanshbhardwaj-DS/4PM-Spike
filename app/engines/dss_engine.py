from typing import Dict, Any, List, Optional
from app.config import RULE_VERSION
from app.engines.completeness import evaluate_completeness
from app.engines.validation import validate_meter_readings_dataset
from app.engines.boundary_solar import analyze_meter_boundary_and_solar
from app.engines.demand import filter_peak_window_readings, compute_demand_metrics
from app.engines.evidence import evaluate_evidence_grade
from app.engines.severity import evaluate_severity
from app.engines.eligibility import evaluate_eligibility
from app.engines.explanations import generate_decision_explanation

def run_dss_deterministic_pipeline(
    building_dict: Dict[str, Any],
    meter_dict: Dict[str, Any],
    readings: List[Dict[str, Any]],
    solar_readings: List[Dict[str, Any]],
    target_dates: List[Any],
    historical_baseline_kw: Optional[float] = None,
    has_physical_inspection_on_record: bool = False,
    has_calibration_cert_on_record: bool = False,
    has_open_tasks: bool = False
) -> Dict[str, Any]:
    """
    Executes the entire deterministic decision pipeline for a single meter/building.
    Same inputs + same rule version => identical deterministic output.
    Does NOT use external AI/LLMs for core decision making.
    """
    building_name = building_dict.get("name", "Unknown Building")
    building_code = building_dict.get("code", "BLD-UNK")
    is_protected = building_dict.get("is_protected", False)
    meter_code = meter_dict.get("meter_code", "MTR-UNK")
    raw_boundary = meter_dict.get("boundary_type", "UNDECLARED")
    meter_status = meter_dict.get("status", "ACTIVE")

    # Step 1: Validation
    cleaned_readings, data_findings, val_summary = validate_meter_readings_dataset(
        readings=readings,
        boundary_type=raw_boundary,
        meter_code=meter_code,
        building_code=building_code
    )

    # Step 2: Completeness
    completeness_metrics = evaluate_completeness(
        readings=cleaned_readings,
        target_dates=target_dates
    )

    # Step 3: Boundary & Solar Alignment
    boundary_analysis = analyze_meter_boundary_and_solar(
        boundary_type=raw_boundary,
        meter_readings=cleaned_readings,
        solar_readings=solar_readings,
        meter_documentation_ref=meter_dict.get("boundary_doc_ref")
    )

    # Step 4: Demand Window Analysis (16:00 to 20:00 exclusive)
    active_readings_for_demand = boundary_analysis.get("reconstructed_readings") or cleaned_readings
    peak_readings = filter_peak_window_readings(active_readings_for_demand)
    demand_metrics = compute_demand_metrics(
        peak_window_readings=peak_readings,
        historical_baseline_kw=historical_baseline_kw
    )

    # Step 5: Evidence Assessment (E0 - E3)
    evidence_metrics = evaluate_evidence_grade(
        completeness_metrics=completeness_metrics,
        boundary_analysis=boundary_analysis,
        data_quality_findings=data_findings,
        has_physical_inspection_on_record=has_physical_inspection_on_record,
        has_calibration_cert_on_record=has_calibration_cert_on_record
    )

    # Step 6: Severity Evaluation (CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL)
    has_negative_spike = any(f.get("issue_category") == "NEGATIVE_VALUES" for f in data_findings)
    severity_metrics = evaluate_severity(
        building_is_protected=is_protected,
        demand_metrics=demand_metrics,
        boundary_analysis=boundary_analysis,
        completeness_metrics=completeness_metrics,
        has_negative_spike_on_gross=has_negative_spike and raw_boundary == "GROSS"
    )

    # Step 7: Eligibility Evaluation (ELIGIBLE, NOT_ELIGIBLE, PENDING_INVESTIGATION, INSUFFICIENT_DATA)
    eligibility_metrics = evaluate_eligibility(
        completeness_metrics=completeness_metrics,
        boundary_analysis=boundary_analysis,
        building_is_protected=is_protected,
        meter_status=meter_status,
        has_open_tasks=has_open_tasks
    )

    # Step 8: Deterministic Decision Code Assignment
    # Priority order:
    # 1. INSUFFICIENT_DATA if completeness fails
    # 2. AUDIT_REGISTER if negative power spikes or register corruption detected
    # 3. RESOLVE_BOUNDARY if boundary is undeclared or conflicting
    # 4. RECOMMEND_SUBMETERING if demand is high / spiking and facility lacks submeters
    # 5. NO_ACTION if demand within normal baseline

    if eligibility_metrics["status"] == "INSUFFICIENT_DATA":
        decision_code = "INSUFFICIENT_DATA"
        recommended_action = (
            f"Recover missing {completeness_metrics['missing_count']} interval readings during the 16:00-20:00 window "
            f"to reach the 90.0% completeness threshold before issuing energy advisories."
        )

    elif has_negative_spike:
        decision_code = "AUDIT_REGISTER"
        recommended_action = (
            f"Dispatch electrician to inspect meter {meter_code} CT connections, wiring polarity, "
            f"and verify register multiplier constants."
        )

    elif not boundary_analysis["is_boundary_resolved"]:
        decision_code = "RESOLVE_BOUNDARY"
        recommended_action = (
            f"Conduct single-line wiring audit on {building_name} switchgear to confirm whether meter {meter_code} "
            f"represents GROSS consumption or NET generation export."
        )

    elif (
        demand_metrics.get("peak_demand_kw", 0) and
        (
            (demand_metrics.get("spike_vs_baseline_pct") is not None and demand_metrics["spike_vs_baseline_pct"] >= 20.0) or
            (demand_metrics.get("historical_baseline_kw") is None and demand_metrics.get("peak_demand_kw", 0) >= 300.0)
        ) and
        meter_dict.get("register_type") != "SUBMETER"
    ):
        decision_code = "RECOMMEND_SUBMETERING"
        recommended_action = (
            f"Peak demand surged to {demand_metrics.get('peak_demand_kw')} kW during the 4 PM spike window. "
            f"Recommend installing branch submetering on high-load circuits (HVAC chiller plant, lab compressors) "
            f"to identify isolated contributors."
        )

    else:
        decision_code = "NO_ACTION"
        recommended_action = (
            f"Energy demand at {building_name} during 16:00-20:00 adheres to standard baseline operating parameters. "
            f"No corrective action required. Maintain routine surveillance."
        )

    # Step 9: Generate 13-Point Universal Decision Explanation
    explanation = generate_decision_explanation(
        decision_code=decision_code,
        building_name=building_name,
        meter_code=meter_code,
        demand_metrics=demand_metrics,
        completeness_metrics=completeness_metrics,
        boundary_analysis=boundary_analysis,
        evidence_metrics=evidence_metrics,
        severity_metrics=severity_metrics,
        eligibility_metrics=eligibility_metrics,
        rule_version=RULE_VERSION
    )

    return {
        "decision_code": decision_code,
        "rule_version": RULE_VERSION,
        "evidence_grade": evidence_metrics["evidence_grade"],
        "severity": severity_metrics["severity"],
        "eligibility": eligibility_metrics["status"],
        "recommended_action": recommended_action,
        "human_review_required": severity_metrics["human_review_required"],
        "explanation": explanation,
        "demand_metrics": demand_metrics,
        "completeness_metrics": completeness_metrics,
        "boundary_analysis": boundary_analysis,
        "evidence_metrics": evidence_metrics,
        "severity_metrics": severity_metrics,
        "eligibility_metrics": eligibility_metrics,
        "data_quality_findings": data_findings,
        "validation_summary": val_summary
    }

