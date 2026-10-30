from typing import List, Optional
from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session
import pandas as pd
import io
from app.database import get_db
from app.models import User, AuditEvent
from app.schemas import AuditEventResponse
from app.auth import get_current_user, require_role

router = APIRouter(prefix="/api/audit", tags=["Audit Logs"])

@router.get("/logs", response_model=List[AuditEventResponse])
def get_audit_logs(
    event_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(AuditEvent)

    if current_user.role == "ELECTRICIAN":
        # Electricians only see their own relevant audit events
        query = query.filter(AuditEvent.user_id == current_user.id)
    # Management / Admin can see all campus audit events

    if event_type:
        query = query.filter(AuditEvent.event_type == event_type)

    logs = query.order_by(AuditEvent.timestamp.desc()).limit(limit).all()
    return logs

@router.get("/export")
def export_audit_logs(
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    logs = db.query(AuditEvent).order_by(AuditEvent.timestamp.desc()).all()
    records = []
    for l in logs:
        records.append({
            "id": l.id,
            "timestamp": l.timestamp.isoformat(),
            "user_id": l.user_id,
            "role": l.role,
            "event_type": l.event_type,
            "entity_type": l.entity_type,
            "entity_id": l.entity_id,
            "details": str(l.action_details),
            "ip_address": l.ip_address
        })

    df = pd.DataFrame(records)
    stream = io.StringIO()
    df.to_csv(stream, index=False)

    return Response(
        content=stream.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=dss_audit_trail.csv"}
    )

