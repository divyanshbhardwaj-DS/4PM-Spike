from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Building, BuildingAssignment, Meter, DSSDecision, InvestigationTask
from app.auth import get_current_user, require_role, verify_electrician_building_access

router = APIRouter(prefix="/api/buildings", tags=["Buildings"])

@router.get("")
def list_buildings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Building)
    if current_user.role == "ELECTRICIAN":
        # Restricted to assigned buildings
        assigned_ids = db.query(BuildingAssignment.building_id).filter(
            BuildingAssignment.user_id == current_user.id
        ).all()
        building_ids = [aid[0] for aid in assigned_ids]
        query = query.filter(Building.id.in_(building_ids))

    buildings = query.all()
    results = []

    for b in buildings:
        # Get latest decision for building
        latest_dec = db.query(DSSDecision).filter(
            DSSDecision.building_id == b.id
        ).order_by(DSSDecision.created_at.desc()).first()

        # Count open tasks
        open_tasks = db.query(InvestigationTask).filter(
            InvestigationTask.building_id == b.id,
            InvestigationTask.status.in_(["ASSIGNED", "IN_PROGRESS", "NEEDS_INFORMATION", "REOPENED"])
        ).count()

        meters = db.query(Meter).filter(Meter.building_id == b.id).all()

        results.append({
            "id": b.id,
            "name": b.name,
            "code": b.code,
            "category": b.category,
            "is_protected": b.is_protected,
            "safety_notes": b.safety_notes,
            "meter_count": len(meters),
            "meters": [{"id": m.id, "meter_code": m.meter_code, "boundary_type": m.boundary_type, "status": m.status} for m in meters],
            "evidence_grade": latest_dec.evidence_grade if latest_dec else "E0",
            "severity": latest_dec.severity if latest_dec else "INFORMATIONAL",
            "eligibility": latest_dec.eligibility if latest_dec else "INSUFFICIENT_DATA",
            "decision_code": latest_dec.decision_code if latest_dec else "NO_ACTION",
            "open_investigation_count": open_tasks
        })

    return results

@router.get("/{building_id}")
def get_building_detail(
    building_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if not verify_electrician_building_access(current_user, building_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You are not assigned to this campus building."
        )

    building = db.query(Building).filter(Building.id == building_id).first()
    if not building:
        raise HTTPException(status_code=404, detail="Building not found.")

    meters = db.query(Meter).filter(Meter.building_id == building.id).all()
    latest_dec = db.query(DSSDecision).filter(
        DSSDecision.building_id == building.id
    ).order_by(DSSDecision.created_at.desc()).first()

    tasks = db.query(InvestigationTask).filter(
        InvestigationTask.building_id == building.id
    ).order_by(InvestigationTask.created_at.desc()).all()

    return {
        "id": building.id,
        "name": building.name,
        "code": building.code,
        "category": building.category,
        "is_protected": building.is_protected,
        "safety_notes": building.safety_notes,
        "meters": [
            {
                "id": m.id,
                "meter_code": m.meter_code,
                "boundary_type": m.boundary_type,
                "register_type": m.register_type,
                "unit": m.unit,
                "status": m.status
            }
            for m in meters
        ],
        "latest_decision": {
            "id": latest_dec.id,
            "decision_code": latest_dec.decision_code,
            "evidence_grade": latest_dec.evidence_grade,
            "severity": latest_dec.severity,
            "eligibility": latest_dec.eligibility,
            "recommended_action": latest_dec.recommended_action,
            "human_review_required": latest_dec.human_review_required,
            "status": latest_dec.status,
            "created_at": latest_dec.created_at.isoformat()
        } if latest_dec else None,
        "tasks": [
            {
                "id": t.id,
                "priority": t.priority,
                "status": t.status,
                "required_inspection": t.required_inspection,
                "instructions": t.instructions,
                "due_date": t.due_date.isoformat() if t.due_date else None
            }
            for t in tasks
        ]
    }

