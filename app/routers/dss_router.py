from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, DSSDecision, DecisionExplanation, Building, BuildingAssignment, Meter
from app.auth import get_current_user, verify_electrician_building_access

router = APIRouter(prefix="/api/dss", tags=["DSS Engine & Explanations"])

@router.get("/decisions")
def list_dss_decisions(
    building_id: Optional[int] = None,
    decision_code: Optional[str] = None,
    severity: Optional[str] = None,
    evidence_grade: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(DSSDecision)

    if current_user.role == "ELECTRICIAN":
        assigned_ids = db.query(BuildingAssignment.building_id).filter(
            BuildingAssignment.user_id == current_user.id
        ).all()
        building_ids = [aid[0] for aid in assigned_ids]
        query = query.filter(DSSDecision.building_id.in_(building_ids))

    if building_id:
        if not verify_electrician_building_access(current_user, building_id, db):
            raise HTTPException(status_code=403, detail="Forbidden: You are not assigned to this building.")
        query = query.filter(DSSDecision.building_id == building_id)

    if decision_code:
        query = query.filter(DSSDecision.decision_code == decision_code)
    if severity:
        query = query.filter(DSSDecision.severity == severity)
    if evidence_grade:
        query = query.filter(DSSDecision.evidence_grade == evidence_grade)
    if status_filter:
        query = query.filter(DSSDecision.status == status_filter)

    decisions = query.order_by(DSSDecision.created_at.desc()).all()
    results = []

    for d in decisions:
        b = db.query(Building).filter(Building.id == d.building_id).first()
        m = db.query(Meter).filter(Meter.id == d.meter_id).first() if d.meter_id else None
        exp = db.query(DecisionExplanation).filter(DecisionExplanation.decision_id == d.id).first()

        results.append({
            "id": d.id,
            "decision_code": d.decision_code,
            "building_id": d.building_id,
            "building_name": b.name if b else "Unknown",
            "building_code": b.code if b else "Unknown",
            "is_protected": b.is_protected if b else False,
            "meter_code": m.meter_code if m else "N/A",
            "rule_version": d.rule_version,
            "evidence_grade": d.evidence_grade,
            "severity": d.severity,
            "eligibility": d.eligibility,
            "recommended_action": d.recommended_action,
            "human_review_required": d.human_review_required,
            "status": d.status,
            "created_at": d.created_at.isoformat(),
            "short_explanation": exp.why_decided if exp else "Explanation available."
        })

    return results

@router.get("/decisions/{decision_id}")
def get_decision_detail(
    decision_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    decision = db.query(DSSDecision).filter(DSSDecision.id == decision_id).first()
    if not decision:
        raise HTTPException(status_code=404, detail="DSS Decision not found.")

    if not verify_electrician_building_access(current_user, decision.building_id, db):
        raise HTTPException(status_code=403, detail="Forbidden: You are not assigned to this building.")

    b = db.query(Building).filter(Building.id == decision.building_id).first()
    m = db.query(Meter).filter(Meter.id == decision.meter_id).first() if decision.meter_id else None
    exp = db.query(DecisionExplanation).filter(DecisionExplanation.decision_id == decision.id).first()

    return {
        "id": decision.id,
        "decision_code": decision.decision_code,
        "building_id": decision.building_id,
        "building_name": b.name if b else "Unknown",
        "building_code": b.code if b else "Unknown",
        "is_protected": b.is_protected if b else False,
        "meter_code": m.meter_code if m else "N/A",
        "rule_version": decision.rule_version,
        "evidence_grade": decision.evidence_grade,
        "severity": decision.severity,
        "eligibility": decision.eligibility,
        "recommended_action": decision.recommended_action,
        "human_review_required": decision.human_review_required,
        "status": decision.status,
        "created_at": decision.created_at.isoformat(),
        "explanation": {
            "what_decided": exp.what_decided if exp else "Explanation unavailable.",
            "why_decided": exp.why_decided if exp else "Explanation unavailable.",
            "data_used_json": exp.data_used_json if exp else {},
            "rule_applied": exp.rule_applied if exp else "RULE-CORE",
            "calculation_details": exp.calculation_details if exp else "N/A",
            "supporting_evidence_json": exp.supporting_evidence_json if exp else {},
            "missing_information": exp.missing_information if exp else "None",
            "uncertainty": exp.uncertainty if exp else "None",
            "what_could_change": exp.what_could_change if exp else "None",
            "recommended_next_step": exp.recommended_next_step if exp else "Review with team",
            "responsible_role": exp.responsible_role if exp else "MANAGEMENT",
            "source_provenance": exp.source_provenance if exp else "DSS Engine",
            "decision_timestamp": exp.created_at.isoformat() if exp else decision.created_at.isoformat()
        } if exp else None
    }

@router.get("/explain-metric")
def explain_arbitrary_metric(
    metric_type: str = Query(..., description="EVIDENCE_GRADE, SEVERITY, ELIGIBILITY, DECISION_CODE, PEAK_WINDOW"),
    value: str = Query(..., description="e.g. E2, CRITICAL, RESOLVE_BOUNDARY, ELIGIBLE"),
    building_id: Optional[int] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Universal 'Why this result?' endpoint powering UI badges and cards.
    Returns the complete 13-point explainability structure.
    """
    m_type = metric_type.upper()
    val = value.upper()

    building_name = "Campus Building"
    if building_id:
        b = db.query(Building).filter(Building.id == building_id).first()
        if b:
            building_name = b.name

    if m_type == "EVIDENCE_GRADE":
        grade_explanations = {
            "E0": {
                "what": f"Evidence Grade E0 (Unverified / Insufficient) assigned to {building_name}.",
                "why": "Dataset has missing intervals (<90% complete), unresolved boundary, or unvalidated negative readings.",
                "rule": "RULE-EVI-00: Fail-safe baseline. Cannot issue verified advisories without minimum telemetry integrity.",
                "calc": "Completeness < 90.0% OR boundary in ['UNDECLARED', 'CONFLICTING'].",
                "missing": "Continuous 15-minute intervals and verified single-line electrical diagram.",
                "uncertainty": "High uncertainty. Numbers cannot be relied upon for energy planning.",
                "what_could_change": "Ingest missing interval readings and confirm physical meter boundary.",
                "next_step": "Dispatch electrician to inspect meter nameplate and retrieve logger buffers.",
                "role": "ELECTRICIAN"
            },
            "E1": {
                "what": f"Evidence Grade E1 (Preliminary Baseline) assigned to {building_name}.",
                "why": "Completeness satisfies the 90% threshold and boundary is declared, but lacks cross-validation or solar alignment.",
                "rule": "RULE-EVI-01: Single-source telemetry with valid 15-minute timestamps.",
                "calc": "Completeness >= 90.0% AND boundary in ['GROSS', 'NET'].",
                "missing": "Multi-stream cross-validation or physical audit record within last 180 days.",
                "uncertainty": "Moderate uncertainty. Single point of failure in sensing chain.",
                "what_could_change": "Synchronize solar inverter logs or conduct physical field audit.",
                "next_step": "Schedule routine verification walk-through.",
                "role": "ELECTRICIAN"
            },
            "E2": {
                "what": f"Evidence Grade E2 (Corroborated Telemetry) assigned to {building_name}.",
                "why": "High-integrity readings (>=95% complete), verified boundary, zero data corruption flags, and synchronized solar data.",
                "rule": "RULE-EVI-02: Multi-source verified interval dataset.",
                "calc": "Completeness >= 95.0% AND zero critical quality anomalies.",
                "missing": "Official certified calibration test certificate on file.",
                "uncertainty": "Low uncertainty. Highly reliable for advisory demand management.",
                "what_could_change": "Upload annual instrument calibration certificate.",
                "next_step": "Proceed with management advisory review.",
                "role": "MANAGEMENT"
            },
            "E3": {
                "what": f"Evidence Grade E3 (Audited Gold Standard) assigned to {building_name}.",
                "why": "100% complete demand window telemetry, certified calibration certificate, and ground-truth electrician inspection on file.",
                "rule": "RULE-EVI-03: Gold standard audited telemetry.",
                "calc": "Completeness = 100.0% AND active calibration certificate AND physical audit verified.",
                "missing": "None. All evidential criteria satisfied.",
                "uncertainty": "Near-zero uncertainty. Certified operational evidence.",
                "what_could_change": "Expiration of annual calibration cycle.",
                "next_step": "Use with highest confidence in engineering and procurement decisions.",
                "role": "MANAGEMENT"
            }
        }
        info = grade_explanations.get(val, grade_explanations["E0"])

    elif m_type == "SEVERITY":
        sev_explanations = {
            "CRITICAL": {
                "what": f"Severity CRITICAL assigned to {building_name}.",
                "why": "Abnormal demand surge on a protected research/data center asset, OR electrical safety violation (reverse current on gross utility feed).",
                "rule": "RULE-SEV-01: Protected facility with spike > 20% OR gross negative power flow.",
                "calc": "is_protected == True AND spike_vs_baseline > 20.0%",
                "missing": "Immediate field safety clearance from senior electrician.",
                "uncertainty": "Low uncertainty. Urgent operational safety priority.",
                "what_could_change": "Electrician field verification resolving abnormal load or wiring fault.",
                "next_step": "Urgent electrician dispatch; notify facility engineering director.",
                "role": "BOTH"
            },
            "HIGH": {
                "what": f"Severity HIGH assigned to {building_name}.",
                "why": "Peak demand exceeded baseline by >= 30% during 16:00-20:00, or unresolved boundary on large load (>300 kW).",
                "rule": "RULE-SEV-03: Demand spike >= 30.0% above historical baseline.",
                "calc": "spike_vs_baseline >= 30.0%",
                "missing": "Granular circuit breakdown of heavy machinery or chiller loads.",
                "uncertainty": "Low uncertainty regarding peak surge occurrence.",
                "what_could_change": "Implementing peak load pre-cooling or shifting equipment operations.",
                "next_step": "Review submetering recommendation and schedule operational audit.",
                "role": "MANAGEMENT"
            },
            "MEDIUM": {
                "what": f"Severity MEDIUM assigned to {building_name}.",
                "why": "Moderate demand spike (15-30% above baseline) or data completeness between 80-90%.",
                "rule": "RULE-SEV-05: 15.0% <= spike_vs_baseline < 30.0%",
                "calc": "spike_vs_baseline between 15% and 30%.",
                "missing": "Investigation into operational schedule shifts in the building.",
                "uncertainty": "Moderate uncertainty.",
                "what_could_change": "Adjusting HVAC thermostat setpoints ahead of 16:00.",
                "next_step": "Coordinate with building facilities coordinator.",
                "role": "MANAGEMENT"
            },
            "LOW": {
                "what": f"Severity LOW assigned to {building_name}.",
                "why": "Mild demand deviation between 5% and 15% above baseline.",
                "rule": "RULE-SEV-07: 5.0% <= spike_vs_baseline < 15.0%",
                "calc": "Minor variance within manageable thresholds.",
                "missing": "None.",
                "uncertainty": "Low uncertainty.",
                "what_could_change": "Seasonal weather changes.",
                "next_step": "Maintain standard telemetry surveillance.",
                "role": "MANAGEMENT"
            },
            "INFORMATIONAL": {
                "what": f"Severity INFORMATIONAL assigned to {building_name}.",
                "why": "Demand strictly conforms to historical baseline envelope (<5% deviation).",
                "rule": "RULE-SEV-08: Normal baseline operating state.",
                "calc": "spike_vs_baseline < 5.0%",
                "missing": "None.",
                "uncertainty": "Low uncertainty.",
                "what_could_change": "Future seasonal shifts.",
                "next_step": "No action needed.",
                "role": "MANAGEMENT"
            }
        }
        info = sev_explanations.get(val, sev_explanations["INFORMATIONAL"])

    elif m_type == "ELIGIBILITY":
        elig_explanations = {
            "ELIGIBLE": {
                "what": f"Eligibility Status: ELIGIBLE for {building_name}.",
                "why": "Dataset passes the mandatory 90.0% completeness threshold, meter boundary is verified, and building passes electrical safety checks.",
                "rule": "RULE-ELG-01: completeness >= 90.0% AND boundary in ['GROSS', 'NET'] AND active hardware status.",
                "calc": "Completeness >= 90% in 16:00-20:00 window. Meter boundary confirmed.",
                "missing": "None. All operational eligibility prerequisites met.",
                "uncertainty": "Low. Dataset and telemetry meet all standards.",
                "what_could_change": "Missing intervals in future logger transmissions or unresolved boundary disputes.",
                "next_step": "Proceed with advisory energy decision generation and review.",
                "role": "MANAGEMENT"
            },
            "NOT_ELIGIBLE": {
                "what": f"Eligibility Status: NOT_ELIGIBLE for {building_name}.",
                "why": "Facility meter is decommissioned, or building is non-electrical / disconnected from campus telemetry network.",
                "rule": "RULE-ELG-02: Facility status is inactive or decommissioned.",
                "calc": "meter_status != 'ACTIVE'",
                "missing": "Re-commissioning documentation and active electrical utility interconnection.",
                "uncertainty": "Low uncertainty regarding ineligibility.",
                "what_could_change": "Re-activation and commissioning of metering hardware.",
                "next_step": "Archive inactive facility records.",
                "role": "MANAGEMENT"
            },
            "PENDING_INVESTIGATION": {
                "what": f"Eligibility Status: PENDING_INVESTIGATION for {building_name}.",
                "why": "An active field investigation task is in progress or meter boundary is UNDECLARED / CONFLICTING.",
                "rule": "RULE-ELG-03: Open field investigation task OR unresolved boundary.",
                "calc": "open_tasks_count > 0 OR boundary_type in ['UNDECLARED', 'CONFLICTING']",
                "missing": "Completion of electrician field inspection and management acceptance of field feedback.",
                "uncertainty": "High uncertainty until electrician field inspection report is submitted.",
                "what_could_change": "Electrician submits verification confirming switchgear topology and boundary.",
                "next_step": "Dispatch electrician to complete assigned field investigation task.",
                "role": "ELECTRICIAN"
            },
            "INSUFFICIENT_DATA": {
                "what": f"Eligibility Status: INSUFFICIENT_DATA for {building_name}.",
                "why": "Data completeness during the 16:00-20:00 demand window falls below the mandatory 90.0% threshold.",
                "rule": "RULE-ELG-04: completeness < 90.0% in primary demand window.",
                "calc": "valid_intervals / expected_intervals < 0.90",
                "missing": "Missing quarter-hour telemetry intervals to satisfy 90% threshold.",
                "uncertainty": "Very high uncertainty. Prohibited from generating advisory load recommendations.",
                "what_could_change": "Query data logger buffer and retrieve missing interval packets.",
                "next_step": "Investigate telemetry communication pipeline and retrieve missing logger packets.",
                "role": "ELECTRICIAN"
            }
        }
        info = elig_explanations.get(val, elig_explanations["INSUFFICIENT_DATA"])

    elif m_type == "DECISION_CODE":
        dec_explanations = {
            "RESOLVE_BOUNDARY": {
                "what": f"DSS Advisory Decision: RESOLVE_BOUNDARY for {building_name}.",
                "why": "Meter boundary is UNDECLARED or CONFLICTING. Cannot distinguish gross building consumption from net export.",
                "rule": "RULE-BND-03: Mandatory boundary classification prior to peak demand management.",
                "calc": "boundary_type in ['UNDECLARED', 'CONFLICTING']",
                "missing": "Single-line electrical diagram and physical meter switchgear nameplate certification.",
                "uncertainty": "High uncertainty regarding true building electrical consumption.",
                "what_could_change": "Substation field audit certifying meter as GROSS or NET.",
                "next_step": "Assign electrician task to verify physical CT wiring and utility boundary.",
                "role": "ELECTRICIAN"
            },
            "AUDIT_REGISTER": {
                "what": f"DSS Advisory Decision: AUDIT_REGISTER for {building_name}.",
                "why": "Sensor reports negative power flow on a gross consumption feed or abnormal register step-function.",
                "rule": "RULE-REG-01: Reverse power flow on gross utility feed indicates wiring defect.",
                "calc": "power_kw < 0 on GROSS meter",
                "missing": "Physical CT polarity test and digital meter multiplier verification.",
                "uncertainty": "Operational and potential electrical safety risk.",
                "what_could_change": "Physical correction of CT leads or sensor recalibration.",
                "next_step": "Immediate electrician dispatch to test Current Transformer wiring.",
                "role": "ELECTRICIAN"
            },
            "RECOMMEND_SUBMETERING": {
                "what": f"DSS Advisory Decision: RECOMMEND_SUBMETERING for {building_name}.",
                "why": "High demand surge (>=20% above baseline) during the 16:00-20:00 4 PM spike window on an un-submetered facility.",
                "rule": "RULE-SUB-01: Demand surge >= 20% on main utility feed lacking submeters.",
                "calc": "peak_demand_kw >= 300 kW AND spike_vs_baseline >= 20.0%",
                "missing": "Branch circuit breakdown (HVAC chiller compressors vs lighting vs lab equipment).",
                "uncertainty": "Known peak spike, but isolated branch load cause cannot be attributed without submetering.",
                "what_could_change": "Installation of IoT submeters on high-load distribution panels.",
                "next_step": "Energy management team to prepare branch submetering installation proposal.",
                "role": "MANAGEMENT"
            },
            "NO_ACTION": {
                "what": f"DSS Advisory Decision: NO_ACTION for {building_name}.",
                "why": "Building demand adheres strictly to historical baseline operating envelope (<10% deviation) with verified data.",
                "rule": "RULE-NOR-01: Measured demand within expected tolerance requires no advisory intervention.",
                "calc": "spike_vs_baseline < 10.0% AND completeness >= 90%",
                "missing": "None. Normal operations verified.",
                "uncertainty": "Low uncertainty. Standard operations confirmed.",
                "what_could_change": "Future unexpected load surges or logger sensor faults.",
                "next_step": "Maintain routine automated telemetry monitoring.",
                "role": "MANAGEMENT"
            },
            "INSUFFICIENT_DATA": {
                "what": f"DSS Advisory Decision: INSUFFICIENT_DATA for {building_name}.",
                "why": "Missing interval readings reduce completeness below the 90.0% threshold. System refuses to guess.",
                "rule": "RULE-CMP-01: Telemetry completeness < 90% precludes advisory decisions.",
                "calc": "valid_intervals < 90% of scheduled intervals (16 per day)",
                "missing": "Missing 15-minute interval logs in the 16:00-20:00 primary demand window.",
                "uncertainty": "Extreme uncertainty. Missing readings must never be zero-filled.",
                "what_could_change": "Re-polling data logger buffer to recover missing packets.",
                "next_step": "Investigate data logger telemetry network connectivity.",
                "role": "ELECTRICIAN"
            }
        }
        info = dec_explanations.get(val, dec_explanations["NO_ACTION"])

    else:
        info = {
            "what": f"{m_type}: {val} for {building_name}.",
            "why": "Evaluated against deterministic campus energy specifications.",
            "rule": "RULE-CORE-V1.0",
            "calc": "Deterministic calculation grounded in validated records.",
            "missing": "None",
            "uncertainty": "Deterministic rule evaluation.",
            "what_could_change": "Updated dataset or approved human review.",
            "next_step": "Review corresponding dashboard section.",
            "role": "MANAGEMENT"
        }

    return {
        "what_decided": info["what"],
        "why_decided": info["why"],
        "data_used_json": {"metric_type": m_type, "value": val, "building": building_name},
        "rule_applied": info["rule"],
        "calculation_details": info["calc"],
        "supporting_evidence_json": {"provenance": "Deterministic Campus DSS Rule Engine"},
        "missing_information": info["missing"],
        "uncertainty": info["uncertainty"],
        "what_could_change": info["what_could_change"],
        "recommended_next_step": info["next_step"],
        "responsible_role": info["role"],
        "source_provenance": "DSS Universal Decision Explanation Engine | Offline Rule-Based",
        "decision_timestamp": "2026-10-30T08:00:00Z"
    }

