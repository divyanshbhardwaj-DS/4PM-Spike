import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import (
    User, Building, Meter, DSSDecision, DecisionExplanation, Recommendation,
    InvestigationTask, ElectricianFeedback, ManagementReview, ManagementOverride,
    DataQualityFinding, BuildingAssignment
)
from app.schemas import (
    InvestigationTaskCreate, InvestigationTaskUpdate, InvestigationTaskResponse,
    ManagementReviewCreate, ManagementOverrideCreate
)
from app.auth import get_current_user, require_role, record_audit_event

router = APIRouter(prefix="/api/management", tags=["Management Operations"])

@router.get("/overview-metrics")
def get_management_overview_metrics(
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Computes all campus management metrics strictly from real stored records.
    Never uses hardcoded figures.
    """
    total_buildings = db.query(Building).count()
    protected_buildings = db.query(Building).filter(Building.is_protected == True).count()

    # Decisions
    latest_decisions = db.query(DSSDecision).all()
    eligible_count = sum(1 for d in latest_decisions if d.eligibility == "ELIGIBLE")
    crit_high_count = sum(1 for d in latest_decisions if d.severity in ["CRITICAL", "HIGH"])
    pending_reviews_count = sum(1 for d in latest_decisions if d.status == "PENDING_REVIEW")

    # Tasks requiring investigation
    open_tasks_count = db.query(InvestigationTask).filter(
        InvestigationTask.status.in_(["ASSIGNED", "IN_PROGRESS", "NEEDS_INFORMATION", "REOPENED"])
    ).count()

    # Data quality issues
    open_dq_count = db.query(DataQualityFinding).filter(DataQualityFinding.status == "OPEN").count()

    # Electrician feedback pending review
    pending_feedback_count = db.query(ElectricianFeedback).filter(
        ElectricianFeedback.status == "PENDING_REVIEW"
    ).count()

    # Unresolved meter boundaries
    unresolved_boundaries_count = db.query(Meter).filter(
        Meter.boundary_type.in_(["UNDECLARED", "CONFLICTING"])
    ).count()

    return {
        "total_buildings": total_buildings,
        "peak_eligible_buildings": eligible_count,
        "buildings_requiring_investigation": open_tasks_count,
        "critical_high_severity_findings": crit_high_count,
        "open_data_quality_issues": open_dq_count,
        "pending_electrician_feedback": pending_feedback_count,
        "pending_management_reviews": pending_reviews_count,
        "protected_buildings": protected_buildings,
        "unresolved_meter_boundaries": unresolved_boundaries_count
    }

@router.get("/tasks")
def list_investigation_tasks(
    building_id: Optional[int] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(InvestigationTask)

    if current_user.role == "ELECTRICIAN":
        # Electrician sees tasks assigned to them or their assigned buildings
        assigned_b_ids = [
            a[0] for a in db.query(BuildingAssignment.building_id).filter(
                BuildingAssignment.user_id == current_user.id
            ).all()
        ]
        query = query.filter(
            (InvestigationTask.assigned_to_user_id == current_user.id) |
            (InvestigationTask.building_id.in_(assigned_b_ids))
        )

    if building_id:
        query = query.filter(InvestigationTask.building_id == building_id)
    if status_filter:
        query = query.filter(InvestigationTask.status == status_filter)

    tasks = query.order_by(InvestigationTask.created_at.desc()).all()
    results = []

    for t in tasks:
        b = db.query(Building).filter(Building.id == t.building_id).first()
        m = db.query(Meter).filter(Meter.id == t.meter_id).first() if t.meter_id else None
        assigned_user = db.query(User).filter(User.id == t.assigned_to_user_id).first() if t.assigned_to_user_id else None

        results.append({
            "id": t.id,
            "building_id": t.building_id,
            "building_name": b.name if b else "Unknown",
            "building_code": b.code if b else "Unknown",
            "meter_code": m.meter_code if m else "N/A",
            "decision_id": t.decision_id,
            "assigned_to_user_id": t.assigned_to_user_id,
            "assigned_to_name": assigned_user.full_name if assigned_user else "Unassigned",
            "priority": t.priority,
            "status": t.status,
            "required_inspection": t.required_inspection,
            "supporting_evidence": t.supporting_evidence,
            "instructions": t.instructions,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "created_at": t.created_at.isoformat(),
            "updated_at": t.updated_at.isoformat()
        })

    return results

@router.post("/tasks", response_model=InvestigationTaskResponse)
def create_investigation_task(
    task_in: InvestigationTaskCreate,
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    b = db.query(Building).filter(Building.id == task_in.building_id).first()
    if not b:
        raise HTTPException(status_code=404, detail="Building not found.")

    new_task = InvestigationTask(
        building_id=task_in.building_id,
        meter_id=task_in.meter_id,
        decision_id=task_in.decision_id,
        assigned_to_user_id=task_in.assigned_to_user_id,
        assigned_by_user_id=current_user.id,
        priority=task_in.priority.upper(),
        status="ASSIGNED",
        required_inspection=task_in.required_inspection,
        instructions=task_in.instructions,
        due_date=task_in.due_date
    )
    db.add(new_task)
    db.commit()
    db.refresh(new_task)

    record_audit_event(
        db=db,
        user_id=current_user.id,
        role=current_user.role,
        event_type="TASK_ASSIGNED",
        entity_type="INVESTIGATION_TASK",
        entity_id=str(new_task.id),
        action_details={
            "building": b.name,
            "priority": new_task.priority,
            "assigned_to_user_id": new_task.assigned_to_user_id,
            "required_inspection": new_task.required_inspection
        }
    )

    return new_task

@router.patch("/tasks/{task_id}")
def update_investigation_task(
    task_id: int,
    task_update: InvestigationTaskUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    task = db.query(InvestigationTask).filter(InvestigationTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found.")

    # Electricians can update status of their tasks
    if current_user.role == "ELECTRICIAN" and task.assigned_to_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden: You can only update tasks assigned to you.")

    valid_statuses = ["ASSIGNED", "IN_PROGRESS", "NEEDS_INFORMATION", "SUBMITTED_FOR_REVIEW", "COMPLETED", "REOPENED"]
    new_status = task_update.status.upper()
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {valid_statuses}")

    old_status = task.status
    task.status = new_status
    if task_update.supporting_evidence:
        task.supporting_evidence = task_update.supporting_evidence
    if task_update.instructions and current_user.role in ["MANAGEMENT", "ADMIN"]:
        task.instructions = task_update.instructions
    task.updated_at = datetime.datetime.utcnow()

    db.commit()

    record_audit_event(
        db=db,
        user_id=current_user.id,
        role=current_user.role,
        event_type="TASK_STATUS_CHANGED",
        entity_type="INVESTIGATION_TASK",
        entity_id=str(task.id),
        action_details={"old_status": old_status, "new_status": new_status}
    )

    return {"message": f"Task status updated to {new_status}.", "task_id": task.id, "status": new_status}

@router.post("/decisions/{decision_id}/review")
def review_dss_decision(
    decision_id: int,
    review_data: ManagementReviewCreate,
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Management reviews DSS recommendation:
    APPROVE, REJECT (mandatory reason), or MODIFY (mandatory reason).
    """
    decision = db.query(DSSDecision).filter(DSSDecision.id == decision_id).first()
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found.")

    action = review_data.action.upper()
    if action not in ["APPROVE", "REJECT", "MODIFY"]:
        raise HTTPException(status_code=400, detail="Action must be APPROVE, REJECT, or MODIFY.")

    if action in ["REJECT", "MODIFY"] and (not review_data.reason or len(review_data.reason.strip()) < 5):
        raise HTTPException(status_code=400, detail=f"Mandatory justification reason required to {action} a recommendation.")

    old_status = decision.status
    if action == "APPROVE":
        decision.status = "APPROVED"
    elif action == "REJECT":
        decision.status = "REJECTED"
    elif action == "MODIFY":
        decision.status = "MODIFIED"

    # Also update Recommendation status
    rec = db.query(Recommendation).filter(Recommendation.decision_id == decision.id).first()
    if rec:
        rec.status = decision.status

    m_review = ManagementReview(
        decision_id=decision.id,
        reviewer_user_id=current_user.id,
        action=action,
        reason=review_data.reason or f"Approved by {current_user.full_name}",
        notes=review_data.notes
    )
    db.add(m_review)
    db.commit()

    record_audit_event(
        db=db,
        user_id=current_user.id,
        role=current_user.role,
        event_type=f"RECOMMENDATION_{action}",
        entity_type="DSS_DECISION",
        entity_id=str(decision.id),
        action_details={
            "action": action,
            "old_status": old_status,
            "new_status": decision.status,
            "reason": review_data.reason
        }
    )

    return {
        "message": f"Recommendation successfully updated with action: {action}.",
        "decision_id": decision.id,
        "status": decision.status,
        "review_id": m_review.id
    }

@router.post("/decisions/{decision_id}/override")
def override_dss_decision(
    decision_id: int,
    override_data: ManagementOverrideCreate,
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Permitted advisory override with mandatory justification.
    PRESERVES original DSS decision, original explanation, original evidence grade, original severity.
    STRICT SAFETY RULE: Cannot override mandatory safety constraints on protected facilities!
    """
    decision = db.query(DSSDecision).filter(DSSDecision.id == decision_id).first()
    if not decision:
        raise HTTPException(status_code=404, detail="Decision not found.")

    building = db.query(Building).filter(Building.id == decision.building_id).first()

    # Safety constraint: Mandatory protection on protected facilities
    if building and building.is_protected and override_data.override_decision_code == "NO_ACTION" and decision.severity == "CRITICAL":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "SAFETY CONSTRAINT VIOLATION: Cannot override CRITICAL safety advisory to NO_ACTION "
                "on a protected research/data center asset without certified physical electrical clearance."
            )
        )

    if not override_data.justification or len(override_data.justification.strip()) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mandatory detailed justification (min 10 characters) required for decision override."
        )

    exp = db.query(DecisionExplanation).filter(DecisionExplanation.decision_id == decision.id).first()

    # Preserve snapshot of original DSS decision
    snapshot = {
        "original_decision_code": decision.decision_code,
        "original_rule_version": decision.rule_version,
        "original_evidence_grade": decision.evidence_grade,
        "original_severity": decision.severity,
        "original_eligibility": decision.eligibility,
        "original_recommended_action": decision.recommended_action,
        "original_explanation": exp.why_decided if exp else "",
        "original_calculation": exp.calculation_details if exp else "",
        "original_timestamp": decision.created_at.isoformat()
    }

    override_record = ManagementOverride(
        original_decision_id=decision.id,
        reviewer_user_id=current_user.id,
        override_decision_code=override_data.override_decision_code,
        override_action=override_data.override_action,
        justification=override_data.justification,
        preserved_original_snapshot=snapshot
    )
    db.add(override_record)

    # Update decision status to OVERRIDDEN (original decision record fields remain preserved)
    decision.status = "OVERRIDDEN"
    db.commit()

    record_audit_event(
        db=db,
        user_id=current_user.id,
        role=current_user.role,
        event_type="DECISION_OVERRIDDEN",
        entity_type="DSS_DECISION",
        entity_id=str(decision.id),
        action_details={
            "original_code": decision.decision_code,
            "override_code": override_data.override_decision_code,
            "justification": override_data.justification,
            "preserved_snapshot": snapshot
        }
    )

    return {
        "message": "Advisory decision override recorded successfully while strictly preserving original DSS findings.",
        "decision_id": decision.id,
        "status": decision.status,
        "override_id": override_record.id,
        "preserved_snapshot": snapshot
    }

@router.get("/human-ai-comparison")
def get_human_ai_decision_comparison(
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Dedicated Human-AI Decision Review comparison table & true statistical summary.
    All figures calculated strictly from stored database entities.
    """
    decisions = db.query(DSSDecision).all()
    comparison_table = []

    pending_count = 0
    approved_count = 0
    rejected_count = 0
    modified_count = 0
    overridden_count = 0

    disagreement_reasons = []

    for d in decisions:
        b = db.query(Building).filter(Building.id == d.building_id).first()
        m = db.query(Meter).filter(Meter.id == d.meter_id).first() if d.meter_id else None
        exp = db.query(DecisionExplanation).filter(DecisionExplanation.decision_id == d.id).first()
        latest_rev = db.query(ManagementReview).filter(ManagementReview.decision_id == d.id).order_by(ManagementReview.created_at.desc()).first()
        latest_ovr = db.query(ManagementOverride).filter(ManagementOverride.original_decision_id == d.id).order_by(ManagementOverride.created_at.desc()).first()

        human_recommendation = d.recommended_action
        human_reason = "Pending management review"
        human_status = d.status

        if d.status == "PENDING_REVIEW":
            pending_count += 1
        elif d.status == "APPROVED":
            approved_count += 1
            human_reason = latest_rev.reason if latest_rev else "Approved without modification"
        elif d.status == "REJECTED":
            rejected_count += 1
            human_reason = latest_rev.reason if latest_rev else "Rejected by management"
            if latest_rev and latest_rev.reason:
                disagreement_reasons.append(latest_rev.reason)
        elif d.status == "MODIFIED":
            modified_count += 1
            human_reason = latest_rev.reason if latest_rev else "Modified by management"
            if latest_rev and latest_rev.reason:
                disagreement_reasons.append(latest_rev.reason)
        elif d.status == "OVERRIDDEN":
            overridden_count += 1
            human_recommendation = latest_ovr.override_action if latest_ovr else "Overridden"
            human_reason = latest_ovr.justification if latest_ovr else "Overridden with justification"
            if latest_ovr and latest_ovr.justification:
                disagreement_reasons.append(latest_ovr.justification)

        comparison_table.append({
            "decision_id": d.id,
            "building_name": b.name if b else "Unknown",
            "building_code": b.code if b else "Unknown",
            "meter_code": m.meter_code if m else "N/A",
            "dss_decision_code": d.decision_code,
            "dss_recommendation": d.recommended_action,
            "dss_reason": exp.why_decided if exp else "Rule-based deduction",
            "dss_evidence_grade": d.evidence_grade,
            "dss_severity": d.severity,
            "dss_status": d.status,
            "human_recommendation": human_recommendation,
            "human_reason": human_reason,
            "human_status": human_status,
            "has_override": latest_ovr is not None
        })

    total_reviewed = approved_count + rejected_count + modified_count + overridden_count
    agreement_rate = round((approved_count / total_reviewed * 100.0), 2) if total_reviewed > 0 else 100.0

    return {
        "summary_statistics": {
            "total_decisions": len(decisions),
            "pending_reviews": pending_count,
            "approved_recommendations": approved_count,
            "rejected_recommendations": rejected_count,
            "modified_recommendations": modified_count,
            "overrides_recorded": overridden_count,
            "total_reviewed": total_reviewed,
            "agreement_rate_pct": agreement_rate,
            "common_disagreement_reasons": disagreement_reasons[:5]
        },
        "comparison_table": comparison_table
    }

