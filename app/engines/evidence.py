from typing import Dict, Any, List

def evaluate_evidence_grade(
    completeness_metrics: Dict[str, Any],
    boundary_analysis: Dict[str, Any],
    data_quality_findings: List[Dict[str, Any]],
    has_physical_inspection_on_record: bool = False,
    has_calibration_cert_on_record: bool = False
) -> Dict[str, Any]:
    """
    Deterministic evaluation of evidence grade (E0, E1, E2, E3).
    Evidence grade indicates evidential certainty and provenance, NOT urgency or severity.
    Human approval must NEVER automatically increase the evidence grade.
    """
    completeness_pct = completeness_metrics.get("completeness_pct", 0.0)
    boundary_type = boundary_analysis.get("boundary_type", "UNDECLARED")
    is_boundary_resolved = boundary_analysis.get("is_boundary_resolved", False)
    has_solar = boundary_analysis.get("has_solar", False)
    solar_aligned = boundary_analysis.get("solar_aligned", False)

    critical_dq_count = sum(1 for f in data_quality_findings if f.get("severity") in ["CRITICAL", "HIGH"])

    grade = "E0"
    meaning = ""
    why_assigned = ""
    missing_evidence = []
    why_higher_not_justified = ""
    required_for_upgrade = []

    # Rule checks from highest to lowest
    if (
        completeness_pct >= 99.0 and
        is_boundary_resolved and
        (not has_solar or solar_aligned) and
        critical_dq_count == 0 and
        has_physical_inspection_on_record and
        has_calibration_cert_on_record
    ):
        grade = "E3"
        meaning = "Audited & Certified Gold Standard Evidence"
        why_assigned = (
            f"100% interval completeness ({completeness_metrics.get('valid_count')}/{completeness_metrics.get('expected_count')}), "
            f"verified {boundary_type} meter boundary, zero high/critical quality anomalies, "
            f"and certified physical inspection & calibration records exist."
        )
        why_higher_not_justified = "E3 is the maximum achievable evidentiary grade in DSS-1.0."
        required_for_upgrade = ["Maintain annual physical calibration logs."]

    elif (
        completeness_pct >= 95.0 and
        is_boundary_resolved and
        (not has_solar or solar_aligned) and
        critical_dq_count == 0
    ):
        grade = "E2"
        meaning = "Corroborated & High Confidence Telemetry"
        why_assigned = (
            f"Completeness is {completeness_pct}% (>=95% required), boundary is confirmed {boundary_type}, "
            f"and no critical data corruptions were identified."
        )
        if not has_physical_inspection_on_record:
            missing_evidence.append("Physical ground-level electrician audit verification")
        if not has_calibration_cert_on_record:
            missing_evidence.append("Official meter calibration certificate")
        why_higher_not_justified = (
            "Cannot assign E3 because E3 requires physical electrician inspection record and meter calibration certificate."
        )
        required_for_upgrade = [
            "Conduct physical meter inspection and submit verification report.",
            "Upload certified meter calibration documentation."
        ]

    elif (
        completeness_pct >= 90.0 and
        is_boundary_resolved and
        critical_dq_count == 0
    ):
        grade = "E1"
        meaning = "Preliminary / Single-Source Baseline Telemetry"
        why_assigned = (
            f"Completeness is {completeness_pct}% (meets basic 90% threshold) and boundary is declared ({boundary_type}), "
            f"but lacks corroborating secondary streams or has unaligned solar telemetry."
        )
        if has_solar and not solar_aligned:
            missing_evidence.append("Synchronized solar generation interval telemetry")
        if completeness_pct < 95.0:
            missing_evidence.append("Interval completeness >= 95%")
        why_higher_not_justified = (
            "Cannot assign E2 because corroborating solar alignment is missing or completeness is below 95%."
        )
        required_for_upgrade = [
            "Achieve >=95% interval completeness.",
            "Align solar generation timestamps with 15-minute interval boundaries if solar present."
        ]

    else:
        grade = "E0"
        meaning = "Unverified / Insufficient or Contradictory Evidence"
        reasons = []
        if completeness_pct < 90.0:
            reasons.append(f"Completeness is only {completeness_pct}% (below mandatory 90% threshold)")
            missing_evidence.append(f"{completeness_metrics.get('missing_count')} missing 15-minute interval readings")
        if not is_boundary_resolved:
            reasons.append(f"Meter boundary is {boundary_type} (unresolved)")
            missing_evidence.append("Verified single-line diagram and official substation meter boundary documentation")
        if critical_dq_count > 0:
            reasons.append(f"{critical_dq_count} critical/high data quality issues detected")
            missing_evidence.append("Resolution of active data corruption / negative power spikes")

        why_assigned = "; ".join(reasons) if reasons else "Dataset fails baseline integrity checks."
        why_higher_not_justified = (
            "Cannot assign E1 or higher because the dataset fails mandatory completeness, boundary resolution, or quality gates."
        )
        required_for_upgrade = [
            "Acquire missing interval telemetry to achieve >= 90% completeness.",
            "Resolve meter boundary classification (GROSS or NET) via physical audit.",
            "Investigate and eliminate corrupt sensor readings."
        ]

    return {
        "evidence_grade": grade,
        "meaning": meaning,
        "why_assigned": why_assigned,
        "supporting_records": {
            "valid_intervals": completeness_metrics.get("valid_count"),
            "expected_intervals": completeness_metrics.get("expected_count"),
            "completeness_pct": completeness_pct,
            "boundary_type": boundary_type,
            "critical_dq_count": critical_dq_count
        },
        "missing_evidence": missing_evidence,
        "why_higher_not_justified": why_higher_not_justified,
        "required_for_upgrade": required_for_upgrade
    }

