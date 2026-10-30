from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, ElectricianFeedback, ManagementReview, Building, Meter, DSSDecision, InvestigationTask
from app.schemas import ElectricianFeedbackCreate, ElectricianFeedbackResponse, ManagementReviewCreate
from app.auth import get_current_user, require_role, verify_electrician_building_access, record_audit_event

router = APIRouter(prefix="/api/feedback", tags=["Human-AI Feedback"])

@router.get("", response_model=List[ElectricianFeedbackResponse])
def list_feedback(
    building_id: Optional[int] = None,
    status_filter: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(ElectricianFeedback)

    if current_user.role == "ELECTRICIAN":
        # Electrician sees their own feedback
        query = query.filter(ElectricianFeedback.user_id == current_user.id)
    # Management / Admin can see all feedback

    if building_id:
        if not verify_electrician_building_access(current_user, building_id, db):
            raise HTTPException(status_code=403, detail="Forbidden: You are not assigned to this building.")
        query = query.filter(ElectricianFeedback.building_id == building_id)

    if status_filter:
        query = query.filter(ElectricianFeedback.status == status_filter)

    feedback_list = query.order_by(ElectricianFeedback.created_at.desc()).all()
    return feedback_list

@router.post("", response_model=ElectricianFeedbackResponse)
def submit_electrician_feedback(
    fb_data: ElectricianFeedbackCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_electrician_building_access(current_user, fb_data.building_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You can only submit feedback for buildings assigned to you."
        )

    # Validate category
    valid_categories = [
        "METER_CONFIGURATION", "METER_BOUNDARY", "SOLAR_MISMATCH",
        "FAULTY_READING", "MISSING_READING", "TIMESTAMP_ISSUE",
        "EQUIPMENT_OBSERVATION", "MAINTENANCE_ISSUE", "OTHER"
    ]
    if fb_data.feedback_category.upper() not in valid_categories:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid feedback category. Allowed: {valid_categories}"
        )

    new_fb = ElectricianFeedback(
        task_id=fb_data.task_id,
        decision_id=fb_data.decision_id,
        user_id=current_user.id,
        building_id=fb_data.building_id,
        meter_id=fb_data.meter_id,
        feedback_category=fb_data.feedback_category.upper(),
        technical_observation=fb_data.technical_observation,
        explanation=fb_data.explanation,
        supporting_evidence=fb_data.supporting_evidence,
        suggested_correction=fb_data.suggested_correction,
        status="PENDING_REVIEW"
    )
    db.add(new_fb)
    db.commit()
    db.refresh(new_fb)

    # If linked to a task, update task status to SUBMITTED_FOR_REVIEW
    if fb_data.task_id:
        task = db.query(InvestigationTask).filter(InvestigationTask.id == fb_data.task_id).first()
        if task:
            task.status = "SUBMITTED_FOR_REVIEW"
            db.commit()

    # Record immutable audit event
    record_audit_event(
        db=db,
        user_id=current_user.id,
        role=current_user.role,
        event_type="FEEDBACK_SUBMITTED",
        entity_type="FEEDBACK",
        entity_id=str(new_fb.id),
        action_details={
            "building_id": fb_data.building_id,
            "category": fb_data.feedback_category,
            "observation": fb_data.technical_observation
        }
    )

    return new_fb

@router.post("/{feedback_id}/review")
def review_electrician_feedback(
    feedback_id: int,
    review_data: ManagementReviewCreate,
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Management review of electrician technical feedback.
    Electricians CANNOT review or approve their own feedback.
    """
    feedback = db.query(ElectricianFeedback).filter(ElectricianFeedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback record not found.")

    if not review_data.reason or len(review_data.reason.strip()) < 5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Mandatory justification reason required for management review action."
        )

    action = review_data.action.upper()
    if action == "ACCEPT_FEEDBACK":
        feedback.status = "ACCEPTED"
    elif action == "REJECT":
        feedback.status = "REJECTED"
    elif action == "CLARIFICATION_REQUESTED":
        feedback.status = "CLARIFICATION_REQUESTED"
    else:
        feedback.status = action

    # Create ManagementReview record
    m_review = ManagementReview(
        feedback_id=feedback.id,
        decision_id=feedback.decision_id,
        reviewer_user_id=current_user.id,
        action=action,
        reason=review_data.reason,
        notes=review_data.notes
    )
    db.add(m_review)
    db.commit()

    # Audit event
    record_audit_event(
        db=db,
        user_id=current_user.id,
        role=current_user.role,
        event_type="FEEDBACK_REVIEWED",
        entity_type="FEEDBACK",
        entity_id=str(feedback.id),
        action_details={
            "action": action,
            "reason": review_data.reason,
            "reviewer": current_user.username
        }
    )

    return {
        "message": f"Feedback successfully reviewed with action: {action}.",
        "feedback_id": feedback.id,
        "new_status": feedback.status,
        "review_id": m_review.id
    }

