from typing import Dict, Any, List

def evaluate_eligibility(
    completeness_metrics: Dict[str, Any],
    boundary_analysis: Dict[str, Any],
    building_is_protected: bool,
    meter_status: str = "ACTIVE",
    has_open_tasks: bool = False
) -> Dict[str, Any]:
    """
    Deterministic evaluation of eligibility status:
    ELIGIBLE, NOT_ELIGIBLE, PENDING_INVESTIGATION, INSUFFICIENT_DATA.
    A building/analysis does NOT become eligible simply because a user approves it.
    """
    completeness_pct = completeness_metrics.get("completeness_pct", 0.0)
    boundary_type = boundary_analysis.get("boundary_type", "UNDECLARED")
    is_boundary_resolved = boundary_analysis.get("is_boundary_resolved", False)

    required_conditions = [
        "15-minute interval completeness in 16:00-20:00 window >= 90.0%",
        "Meter boundary officially certified as GROSS or NET",
        "Meter hardware status is ACTIVE",
        "No open conflicting investigation tasks blocking baseline certification",
        "Building safety clearance verified for operational advisory intervention"
    ]

    passed_conditions = []
    failed_conditions = []
    missing_information = []
    conditions_for_reconsideration = []

    # Check 1: Completeness
    if completeness_pct >= 90.0:
        passed_conditions.append(f"Completeness is {completeness_pct}% (>= 90% required)")
    else:
        failed_conditions.append(f"Completeness is only {completeness_pct}% (< 90% required)")
        missing_information.append(f"{completeness_metrics.get('missing_count')} missing 15-minute readings in the 16:00-20:00 window")
        conditions_for_reconsideration.append("Ingest missing telemetry to restore completeness above 90.0%")

    # Check 2: Boundary
    if is_boundary_resolved:
        passed_conditions.append(f"Meter boundary certified as {boundary_type}")
    else:
        failed_conditions.append(f"Meter boundary is {boundary_type} (unresolved)")
        missing_information.append("Certified substation boundary documentation (GROSS or NET)")
        conditions_for_reconsideration.append("Electrician physical nameplate audit to certify meter boundary type")

    # Check 3: Meter status
    if meter_status.upper() == "ACTIVE":
        passed_conditions.append("Meter hardware status is ACTIVE")
    else:
        failed_conditions.append(f"Meter hardware status is {meter_status}")
        conditions_for_reconsideration.append("Repair or re-commission meter hardware")

    # Check 4: Open tasks
    if not has_open_tasks:
        passed_conditions.append("No blocking pending investigation tasks")
    else:
        failed_conditions.append("Active pending investigation task in progress")
        conditions_for_reconsideration.append("Complete assigned investigation task and submit electrician review")

    # Check 5: Safety check on protected buildings
    if not building_is_protected:
        passed_conditions.append("Standard campus facility (no life-safety or cryogenic research override restrictions)")
    else:
        passed_conditions.append("Protected facility detected: strict non-invasive advisory protocols apply")

    # Determine status
    if completeness_pct < 90.0 or completeness_metrics.get("valid_count", 0) == 0:
        status = "INSUFFICIENT_DATA"
        reason = f"Data completeness of {completeness_pct}% does not satisfy the mandatory 90% threshold for analysis."
    elif has_open_tasks or not is_boundary_resolved:
        status = "PENDING_INVESTIGATION"
        reason = f"Investigation required: boundary is {boundary_type} or field task is currently pending."
    elif meter_status.upper() != "ACTIVE":
        status = "NOT_ELIGIBLE"
        reason = f"Meter status is {meter_status}, disqualifying it from active advisory recommendations."
    else:
        status = "ELIGIBLE"
        reason = "All mandatory data completeness, boundary verification, and safety criteria are fully satisfied."

    return {
        "status": status,
        "reason": reason,
        "required_conditions": required_conditions,
        "passed_conditions": passed_conditions,
        "failed_conditions": failed_conditions,
        "expected_count": completeness_metrics.get("expected_count"),
        "valid_count": completeness_metrics.get("valid_count"),
        "completeness_pct": completeness_pct,
        "boundary_type": boundary_type,
        "missing_information": missing_information,
        "conditions_for_reconsideration": conditions_for_reconsideration
    }

