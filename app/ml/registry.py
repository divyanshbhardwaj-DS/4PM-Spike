from sqlalchemy.orm import Session
from app.models import Model, ModelVersion, ModelEvaluation, AuditEvent
from app.auth import record_audit_event

def register_model_version(
    db: Session,
    model_name: str,
    task_type: str,
    model_type: str,
    dataset_version_id: int,
    train_period: str,
    test_period: str,
    features_used: list,
    metrics: dict,
    baseline_metrics: dict,
    comparison_summary: str,
    model_path: str,
    limitations: str,
    user_id: int
) -> ModelVersion:
    # Find or create Model
    model = db.query(Model).filter(Model.name == model_name).first()
    if not model:
        model = Model(name=model_name, task_type=task_type, description=f"Predictive model for {task_type}")
        db.add(model)
        db.commit()

    latest_ver = db.query(ModelVersion).filter(ModelVersion.model_id == model.id).order_by(ModelVersion.version_num.desc()).first()
    ver_num = (latest_ver.version_num + 1) if latest_ver else 1

    mv = ModelVersion(
        model_id=model.id,
        version_num=ver_num,
        model_type=model_type,
        dataset_version_id=dataset_version_id,
        training_period=train_period,
        test_period=test_period,
        features_used=features_used,
        metrics_json=metrics,
        status="TRAINED",
        limitations=limitations,
        model_path=model_path
    )
    db.add(mv)
    db.commit()

    evaluation = ModelEvaluation(
        model_version_id=mv.id,
        mae=metrics.get("mae"),
        rmse=metrics.get("rmse"),
        mape=metrics.get("mape"),
        baseline_mae=baseline_metrics.get("baseline_mae"),
        baseline_rmse=baseline_metrics.get("baseline_rmse"),
        comparison_summary=comparison_summary,
        human_verified=False
    )
    db.add(evaluation)
    db.commit()

    return mv

