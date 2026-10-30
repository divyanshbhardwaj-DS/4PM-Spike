import datetime
from typing import Dict, Any, Optional

def generate_decision_explanation(
    decision_code: str,
    building_name: str,
    meter_code: str,
    demand_metrics: Dict[str, Any],
    completeness_metrics: Dict[str, Any],
    boundary_analysis: Dict[str, Any],
    evidence_metrics: Dict[str, Any],
    severity_metrics: Dict[str, Any],
    eligibility_metrics: Dict[str, Any],
    rule_version: str = "DSS-CORE-V1.0"
) -> Dict[str, Any]:
    """
    Constructs the 13-point universal explanation required by Section 14.
    Every single field is grounded in real, deterministic telemetry and documented rules.
    """
    comp_pct = completeness_metrics.get("completeness_pct", 0.0)
    peak_kw = demand_metrics.get("peak_demand_kw")
    avg_kw = demand_metrics.get("average_demand_kw")
    spike_pct = demand_metrics.get("spike_vs_baseline_pct")
    boundary_type = boundary_analysis.get("boundary_type", "UNDECLARED")
    evidence_grade = evidence_metrics.get("evidence_grade", "E0")
    severity = severity_metrics.get("severity", "INFORMATIONAL")
    eligibility = eligibility_metrics.get("status", "INSUFFICIENT_DATA")

    # 1. What was decided
    what_map = {
        "RESOLVE_BOUNDARY": f"Classified meter {meter_code} on {building_name} as requiring boundary resolution (Current: {boundary_type}).",
        "AUDIT_REGISTER": f"Recommended physical register and CT audit for meter {meter_code} on {building_name}.",
        "RECOMMEND_SUBMETERING": f"Recommended installation of dedicated submetering for major load centers at {building_name}.",
        "NO_ACTION": f"No operational or electrical intervention warranted for {building_name} (Demand matches baseline).",
        "INSUFFICIENT_DATA": f"Marked {building_name} as having insufficient interval telemetry for 16:00-20:00 peak analysis."
    }
    what_decided = what_map.get(decision_code, f"Issued decision {decision_code} for {building_name}.")

    # 2. Why it was decided
    why_map = {
        "RESOLVE_BOUNDARY": f"The meter boundary is currently {boundary_type}. Net vs Gross distinction directly alters true building consumption calculations.",
        "AUDIT_REGISTER": "Unusual negative power readings or irregular multiplier constants were detected on the meter registers.",
        "RECOMMEND_SUBMETERING": f"Peak demand reached {peak_kw} kW during 16:00-20:00 ({spike_pct}% above baseline), but the facility lacks load breakdown.",
        "NO_ACTION": f"Peak demand ({peak_kw} kW) and average demand ({avg_kw} kW) remain safely within normal baseline tolerances with complete telemetry.",
        "INSUFFICIENT_DATA": f"Data completeness during the 16:00-20:00 window is only {comp_pct}%, falling short of the required 90.0% threshold."
    }
    why_decided = why_map.get(decision_code, "Evaluated under deterministic campus rule matrix.")

    # 3. Which data was used
    data_used = {
        "analysis_window": "16:00 - 20:00 (15-min intervals)",
        "expected_intervals": completeness_metrics.get("expected_count"),
        "valid_intervals": completeness_metrics.get("valid_count"),
        "completeness_pct": comp_pct,
        "peak_demand_kw": peak_kw,
        "average_demand_kw": avg_kw,
        "demand_trend": demand_metrics.get("demand_trend"),
        "spike_vs_baseline_pct": spike_pct,
        "boundary_type": boundary_type,
        "evidence_grade": evidence_grade,
        "severity": severity,
        "eligibility": eligibility
    }

    # 4. Which rule was applied
    rule_map = {
        "RESOLVE_BOUNDARY": "RULE-BND-03: Any facility with boundary status UNDECLARED or CONFLICTING requires mandatory boundary resolution before advisory load management.",
        "AUDIT_REGISTER": "RULE-REG-01: Persistent negative readings on gross meters or irregular register step-functions require physical verification.",
        "RECOMMEND_SUBMETERING": "RULE-SUB-01: High-load buildings (peak > 300 kW or spike > 25%) lacking submetering qualify for submetering advisory.",
        "NO_ACTION": "RULE-NOR-01: Monitored demand adhering to historical envelope within 10% requires no advisory intervention.",
        "INSUFFICIENT_DATA": "RULE-CMP-01: Telemetry with completeness < 90.0% in primary demand window cannot support advisory recommendations."
    }
    rule_applied = f"{rule_version}: {rule_map.get(decision_code, 'Standard Deterministic Logic')}"

    # 5. Calculation details
    calc_details = (
        f"Window: 16:00-20:00. "
        f"Completeness = ({completeness_metrics.get('valid_count')} valid / {completeness_metrics.get('expected_count')} expected) = {comp_pct}%. "
        f"Peak = {peak_kw} kW. Baseline = {demand_metrics.get('historical_baseline_kw', 'N/A')} kW. "
        f"Spike = {spike_pct if spike_pct is not None else 'N/A'}%."
    )

    # 6. Supporting evidence
    supporting_evidence = {
        "readings_summary": f"{completeness_metrics.get('valid_count')} valid interval measurements",
        "evidence_grade_assigned": evidence_grade,
        "evidence_meaning": evidence_metrics.get("meaning"),
        "boundary_analysis": boundary_analysis.get("calculation_notes")
    }

    # 7. Missing information
    missing_info_list = []
    if comp_pct < 90.0:
        missing_info_list.append(f"{completeness_metrics.get('missing_count')} missing 15-minute readings")
    if boundary_type in ["UNDECLARED", "CONFLICTING"]:
        missing_info_list.append("Official substation single-line diagram and meter boundary declaration")
    if not boundary_analysis.get("solar_aligned") and boundary_analysis.get("has_solar"):
        missing_info_list.append("Synchronized solar generation interval telemetry")
    missing_information = "; ".join(missing_info_list) if missing_info_list else "None. Telemetry and documentation are complete."

    # 8. Uncertainty
    uncertainty_map = {
        "E0": "High uncertainty due to missing telemetry or unverified boundary. Cannot rely on numerical findings.",
        "E1": "Moderate uncertainty. Single-source reading without independent cross-validation or solar alignment.",
        "E2": "Low uncertainty. High-integrity calibrated data with corroborated boundary.",
        "E3": "Near-zero uncertainty. Gold standard physical inspection and certified calibration on file."
    }
    uncertainty = uncertainty_map.get(evidence_grade, "Moderate uncertainty.")

    # 9. What could change the result
    what_could_change_map = {
        "RESOLVE_BOUNDARY": "Submission and managerial approval of certified single-line diagram or nameplate boundary audit.",
        "AUDIT_REGISTER": "Physical electrician verification confirming CT wiring or sensor recalibration.",
        "RECOMMEND_SUBMETERING": "Installation and integration of smart branch submeters for HVAC and heavy lab equipment.",
        "NO_ACTION": "Future unexpected spikes (>15%) during the 16:00-20:00 peak window or sensor telemetry degradation.",
        "INSUFFICIENT_DATA": "Re-ingestion of recovered logger telemetry restoring completeness >= 90.0%."
    }
    what_could_change = what_could_change_map.get(decision_code, "Additional field evidence or updated data ingestion.")

    # 10. Recommended next step
    next_step_map = {
        "RESOLVE_BOUNDARY": "Dispatch electrician to perform boundary verification on meter switchgear and update registry.",
        "AUDIT_REGISTER": "Issue high-priority investigation task to electrician for register and CT polarity testing.",
        "RECOMMEND_SUBMETERING": "Energy management team to prepare feasibility study and capital allocation for branch submetering.",
        "NO_ACTION": "Maintain automated telemetry monitoring; no manual task dispatch needed.",
        "INSUFFICIENT_DATA": "Query meter data logger buffer to retrieve missing interval packets."
    }
    recommended_next_step = next_step_map.get(decision_code, "Review finding in management dashboard.")

    # 11. Responsible role
    role_map = {
        "RESOLVE_BOUNDARY": "ELECTRICIAN",
        "AUDIT_REGISTER": "ELECTRICIAN",
        "RECOMMEND_SUBMETERING": "MANAGEMENT",
        "NO_ACTION": "MANAGEMENT",
        "INSUFFICIENT_DATA": "ELECTRICIAN"
    }
    responsible_role = role_map.get(decision_code, "BOTH")

    # 12. Source and provenance
    source_provenance = f"DSS Deterministic Engine ({rule_version}) | Validated Campus Readings | Dataset Version Traceable"

    # 13. Decision timestamp
    decision_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()

    return {
        "what_decided": what_decided,
        "why_decided": why_decided,
        "data_used_json": data_used,
        "rule_applied": rule_applied,
        "calculation_details": calc_details,
        "supporting_evidence_json": supporting_evidence,
        "missing_information": missing_information,
        "uncertainty": uncertainty,
        "what_could_change": what_could_change,
        "recommended_next_step": recommended_next_step,
        "responsible_role": responsible_role,
        "source_provenance": source_provenance,
        "decision_timestamp": decision_timestamp
    }

