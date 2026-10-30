from typing import Dict, Any, Optional

def evaluate_severity(
    building_is_protected: bool,
    demand_metrics: Dict[str, Any],
    boundary_analysis: Dict[str, Any],
    completeness_metrics: Dict[str, Any],
    has_negative_spike_on_gross: bool = False
) -> Dict[str, Any]:
    """
    Deterministic evaluation of finding severity:
    CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL.
    Severity indicates urgency and operational risk, NOT evidentiary certainty.
    """
    spike_pct = demand_metrics.get("spike_vs_baseline_pct")
    peak_kw = demand_metrics.get("peak_demand_kw", 0.0) or 0.0
    boundary_type = boundary_analysis.get("boundary_type", "UNDECLARED")
    completeness_pct = completeness_metrics.get("completeness_pct", 0.0)

    severity = "INFORMATIONAL"
    triggering_condition = ""
    applied_threshold = ""
    why_applies = ""
    why_others_do_not = ""
    recommended_action = ""
    responsible_role = "MANAGEMENT"
    human_review_required = True

    # Rule 1: CRITICAL
    if (building_is_protected and spike_pct is not None and spike_pct > 20.0):
        severity = "CRITICAL"
        triggering_condition = "Protected facility experiencing abnormal peak demand spike (>20% above baseline)"
        applied_threshold = "RULE-SEV-01: Protected building with spike_vs_baseline_pct > 20.0%"
        why_applies = (
            f"The facility is designated PROTECTED and observed a {spike_pct}% demand surge reaching {peak_kw} kW. "
            f"Advisory intervention must be urgently reviewed to protect mission-critical equipment and research assets."
        )
        why_others_do_not = "Elevated from High because protected facility status elevates operational risk to campus continuity."
        recommended_action = "Dispatch senior electrician for non-invasive thermal and circuit inspection; alert facility engineering manager."
        responsible_role = "BOTH"
        human_review_required = True

    elif has_negative_spike_on_gross:
        severity = "CRITICAL"
        triggering_condition = "Gross consumption meter reporting reverse power flow (< -50 kW or active short/reversal)"
        applied_threshold = "RULE-SEV-02: Gross meter with negative active power"
        why_applies = "Reverse current flow on a main gross utility feed indicates potential CT wiring reversal or severe grid sync fault."
        why_others_do_not = "Electrical and fire safety concerns override standard operational severity levels."
        recommended_action = "Immediate electrician dispatch to test Current Transformer (CT) polarity and switchgear isolation."
        responsible_role = "ELECTRICIAN"
        human_review_required = True

    # Rule 2: HIGH
    elif (spike_pct is not None and spike_pct >= 30.0):
        severity = "HIGH"
        triggering_condition = "Peak demand during 16:00-20:00 exceeds historical baseline by >= 30.0%"
        applied_threshold = "RULE-SEV-03: spike_vs_baseline_pct >= 30.0%"
        why_applies = f"Peak demand reached {peak_kw} kW, which is {spike_pct}% above the historical baseline."
        why_others_do_not = "Not Critical because the building is not designated as a protected life-safety/data center asset."
        recommended_action = "Initiate submetering investigation and schedule electrician walk-through during the 16:00-20:00 peak window."
        responsible_role = "MANAGEMENT"
        human_review_required = True

    elif (boundary_type in ["CONFLICTING", "UNDECLARED"] and peak_kw >= 300.0):
        severity = "HIGH"
        triggering_condition = "Unresolved meter boundary on high-load facility (peak demand >= 300 kW)"
        applied_threshold = "RULE-SEV-04: Boundary unresolved AND peak_demand_kw >= 300.0"
        why_applies = f"Building draws significant load ({peak_kw} kW) while boundary classification is {boundary_type}."
        why_others_do_not = "High volume of power makes accounting errors material to campus energy budgets."
        recommended_action = "Assign electrician to audit physical meter nameplate and single-line diagrams to resolve boundary."
        responsible_role = "ELECTRICIAN"
        human_review_required = True

    # Rule 3: MEDIUM
    elif (spike_pct is not None and spike_pct >= 15.0):
        severity = "MEDIUM"
        triggering_condition = "Moderate peak demand spike between 15% and 30% above baseline"
        applied_threshold = "RULE-SEV-05: 15.0% <= spike_vs_baseline_pct < 30.0%"
        why_applies = f"Peak demand rose {spike_pct}% above baseline, warranting operational attention."
        why_others_do_not = "Below the 30% threshold for High severity; above the 15% threshold for Low."
        recommended_action = "Review building scheduling and HVAC pre-cooling routines ahead of the 16:00 window."
        responsible_role = "MANAGEMENT"
        human_review_required = True

    elif (completeness_pct < 90.0):
        severity = "MEDIUM"
        triggering_condition = f"Data completeness ({completeness_pct}%) is below the mandatory 90% threshold"
        applied_threshold = "RULE-SEV-06: completeness_pct < 90.0%"
        why_applies = f"Missing interval telemetry prevents definitive peak characterization."
        why_others_do_not = "Data telemetry gap is an operational hindrance but does not represent physical equipment failure."
        recommended_action = "Investigate data logger connectivity and recover missing interval logs."
        responsible_role = "ELECTRICIAN"
        human_review_required = False

    # Rule 4: LOW
    elif (spike_pct is not None and spike_pct >= 5.0):
        severity = "LOW"
        triggering_condition = "Mild demand deviation between 5% and 15% above baseline"
        applied_threshold = "RULE-SEV-07: 5.0% <= spike_vs_baseline_pct < 15.0%"
        why_applies = f"Minor fluctuation of {spike_pct}% within manageable campus tolerances."
        why_others_do_not = "Does not exhibit sharp peak characteristics."
        recommended_action = "Continue automated monitoring; no active intervention required."
        responsible_role = "MANAGEMENT"
        human_review_required = False

    # Rule 5: INFORMATIONAL
    else:
        severity = "INFORMATIONAL"
        triggering_condition = "Demand profile adheres to standard expected baseline (< 5% deviation)"
        applied_threshold = "RULE-SEV-08: Normal operating conditions"
        why_applies = "All monitored metrics fall within acceptable baseline operating envelopes."
        why_others_do_not = "No anomalous patterns or telemetry violations were detected."
        recommended_action = "Maintain regular surveillance."
        responsible_role = "MANAGEMENT"
        human_review_required = False

    return {
        "severity": severity,
        "triggering_condition": triggering_condition,
        "applied_threshold": applied_threshold,
        "why_applies": why_applies,
        "why_others_do_not": why_others_do_not,
        "recommended_action": recommended_action,
        "responsible_role": responsible_role,
        "human_review_required": human_review_required
    }

