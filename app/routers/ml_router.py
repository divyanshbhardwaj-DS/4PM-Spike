from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Model, ModelVersion, ModelEvaluation, MeterReading, DatasetVersion
from app.auth import get_current_user, require_role, record_audit_event
from app.ml.suitability import assess_ml_suitability
from app.ml.trainer import train_demand_forecast_model
from app.ml.registry import register_model_version

router = APIRouter(prefix="/api/ml", tags=["Machine Learning & Model Governance"])

class ModelTrainRequest(BaseModel):
    dataset_version_id: int
    task_type: str = "PEAK_FORECASTING"
    model_type: str = "RIDGE_REGRESSION" # RIDGE_REGRESSION, RANDOM_FOREST
    model_name: str = "Peak Demand Forecaster"

class ModelActionRequest(BaseModel):
    action: str # APPROVE, REJECT, ACTIVATE, ROLLBACK
    notes: Optional[str] = None

@router.get("/suitability")
def check_dataset_suitability(
    dataset_version_id: int = Query(..., description="ID of dataset version to assess"),
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    version = db.query(DatasetVersion).filter(DatasetVersion.id == dataset_version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found.")

    readings = db.query(MeterReading).filter(
        MeterReading.dataset_version_id == version.id
    ).order_by(MeterReading.timestamp.asc()).all()

    record_dicts = [
        {"timestamp": r.timestamp, "power_kw": r.power_kw, "is_valid": r.is_valid}
        for r in readings
    ]

    suitability = assess_ml_suitability(record_dicts, task_type="PEAK_FORECASTING")
    return {
        "dataset_version_id": version.id,
        "dataset_version_num": version.version_num,
        "suitability": suitability
    }

@router.post("/train")
def train_model(
    req: ModelTrainRequest,
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    version = db.query(DatasetVersion).filter(DatasetVersion.id == req.dataset_version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found.")

    readings = db.query(MeterReading).filter(
        MeterReading.dataset_version_id == version.id
    ).order_by(MeterReading.timestamp.asc()).all()

    record_dicts = [
        {"timestamp": r.timestamp, "power_kw": r.power_kw, "is_valid": r.is_valid}
        for r in readings
    ]

    # Pre-flight suitability check
    suitability = assess_ml_suitability(record_dicts, task_type=req.task_type)
    if not suitability["is_suitable"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Dataset is not suitable for ML training: {suitability['reason']}"
        )

    try:
        train_result = train_demand_forecast_model(
            readings=record_dicts,
            model_type=req.model_type,
            split_ratio=0.80
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Model training error: {str(e)}")

    # Register Model Version
    mv = register_model_version(
        db=db,
        model_name=req.model_name,
        task_type=req.task_type,
        model_type=train_result["model_type"],
        dataset_version_id=version.id,
        train_period=train_result["training_period"],
        test_period=train_result["test_period"],
        features_used=train_result["features_used"],
        metrics=train_result["metrics"],
        baseline_metrics=train_result["baseline_metrics"],
        comparison_summary=train_result["comparison_summary"],
        model_path=train_result["model_path"],
        limitations=train_result["limitations"],
        user_id=current_user.id
    )

    record_audit_event(
        db=db,
        user_id=current_user.id,
        role=current_user.role,
        event_type="MODEL_TRAINED",
        entity_type="MODEL_VERSION",
        entity_id=str(mv.id),
        action_details={
            "model_type": train_result["model_type"],
            "mae": train_result["metrics"]["mae"],
            "rmse": train_result["metrics"]["rmse"],
            "baseline_mae": train_result["baseline_metrics"]["baseline_mae"]
        }
    )

    return {
        "message": "Candidate model successfully trained and registered. Awaiting management review.",
        "model_version_id": mv.id,
        "version_num": mv.version_num,
        "model_type": mv.model_type,
        "metrics": train_result["metrics"],
        "baseline_metrics": train_result["baseline_metrics"],
        "comparison_summary": train_result["comparison_summary"],
        "limitations": train_result["limitations"],
        "governance_note": "Predictions are labeled strictly as statistical estimates; they do not overwrite meter telemetry or deterministic DSS rules."
    }

@router.get("/models")
def list_models(
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    models = db.query(Model).all()
    results = []
    for m in models:
        versions = db.query(ModelVersion).filter(ModelVersion.model_id == m.id).order_by(ModelVersion.version_num.desc()).all()
        results.append({
            "id": m.id,
            "name": m.name,
            "task_type": m.task_type,
            "description": m.description,
            "versions": [
                {
                    "id": v.id,
                    "version_num": v.version_num,
                    "model_type": v.model_type,
                    "status": v.status,
                    "training_period": v.training_period,
                    "test_period": v.test_period,
                    "metrics": v.metrics_json,
                    "features_used": v.features_used,
                    "limitations": v.limitations,
                    "created_at": v.created_at.isoformat()
                }
                for v in versions
            ]
        })
    return results

@router.post("/models/{version_id}/action")
def manage_model_version(
    version_id: int,
    action_req: ModelActionRequest,
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    mv = db.query(ModelVersion).filter(ModelVersion.id == version_id).first()
    if not mv:
        raise HTTPException(status_code=404, detail="Model version not found.")

    action = action_req.action.upper()
    if action not in ["APPROVE", "REJECT", "ACTIVATE", "ROLLBACK"]:
        raise HTTPException(status_code=400, detail="Invalid action. Allowed: APPROVE, REJECT, ACTIVATE, ROLLBACK")

    old_status = mv.status
    if action == "APPROVE":
        mv.status = "APPROVED"
    elif action == "REJECT":
        mv.status = "REJECTED"
    elif action == "ACTIVATE":
        # Deactivate any currently active version for this model
        db.query(ModelVersion).filter(
            ModelVersion.model_id == mv.model_id,
            ModelVersion.status == "ACTIVE"
        ).update({"status": "APPROVED"})
        mv.status = "ACTIVE"
    elif action == "ROLLBACK":
        mv.status = "RETIRED"
        # Find previous approved version
        prev = db.query(ModelVersion).filter(
            ModelVersion.model_id == mv.model_id,
            ModelVersion.version_num < mv.version_num,
            ModelVersion.status.in_(["APPROVED", "RETIRED"])
        ).order_by(ModelVersion.version_num.desc()).first()
        if prev:
            prev.status = "ACTIVE"

    db.commit()

    record_audit_event(
        db=db,
        user_id=current_user.id,
        role=current_user.role,
        event_type=f"MODEL_{action}",
        entity_type="MODEL_VERSION",
        entity_id=str(mv.id),
        action_details={"old_status": old_status, "new_status": mv.status, "notes": action_req.notes}
    )

    return {"message": f"Model version successfully updated with action {action}.", "model_version_id": mv.id, "new_status": mv.status}

