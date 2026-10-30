import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship
from app.database import Base

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(100), nullable=False)
    role = Column(String(20), nullable=False)  # ELECTRICIAN, MANAGEMENT, ADMIN
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utcnow)

    assignments = relationship("BuildingAssignment", back_populates="user", cascade="all, delete-orphan")
    feedback = relationship("ElectricianFeedback", back_populates="user")
    reviews = relationship("ManagementReview", back_populates="reviewer")
    audit_events = relationship("AuditEvent", back_populates="user")
    assigned_tasks = relationship("InvestigationTask", foreign_keys="InvestigationTask.assigned_to_user_id", back_populates="assigned_to")
    created_tasks = relationship("InvestigationTask", foreign_keys="InvestigationTask.assigned_by_user_id", back_populates="assigned_by")


class Building(Base):
    __tablename__ = "buildings"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    code = Column(String(20), unique=True, index=True, nullable=False)
    category = Column(String(50), nullable=False)  # ACADEMIC, RESEARCH, LAB, RESIDENTIAL, RECREATION, UTILITY, ADMIN
    is_protected = Column(Boolean, default=False)  # True for data centers, biosafety, cryogenics, animal care
    safety_notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    meters = relationship("Meter", back_populates="building", cascade="all, delete-orphan")
    solar_readings = relationship("SolarReading", back_populates="building")
    assignments = relationship("BuildingAssignment", back_populates="building", cascade="all, delete-orphan")
    tasks = relationship("InvestigationTask", back_populates="building")
    findings = relationship("DataQualityFinding", back_populates="building")
    decisions = relationship("DSSDecision", back_populates="building")


class BuildingAssignment(Base):
    __tablename__ = "building_assignments"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False)
    assigned_at = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="assignments")
    building = relationship("Building", back_populates="assignments")


class Meter(Base):
    __tablename__ = "meters"

    id = Column(Integer, primary_key=True, index=True)
    meter_code = Column(String(50), unique=True, index=True, nullable=False)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False)
    boundary_type = Column(String(20), default="UNDECLARED")  # GROSS, NET, UNDECLARED, CONFLICTING
    register_type = Column(String(50), default="MAIN_FEED")   # MAIN_FEED, SUBMETER, REGISTER_A, REGISTER_B
    unit = Column(String(20), default="kW")
    status = Column(String(20), default="ACTIVE")             # ACTIVE, FAULTY, AUDIT_REQUIRED, DECOMMISSIONED
    created_at = Column(DateTime, default=utcnow)

    building = relationship("Building", back_populates="meters")
    readings = relationship("MeterReading", back_populates="meter", cascade="all, delete-orphan")
    solar_readings = relationship("SolarReading", back_populates="meter")
    boundary = relationship("MeterBoundary", back_populates="meter", uselist=False, cascade="all, delete-orphan")
    tasks = relationship("InvestigationTask", back_populates="meter")
    findings = relationship("DataQualityFinding", back_populates="meter")
    decisions = relationship("DSSDecision", back_populates="meter")


class MeterBoundary(Base):
    __tablename__ = "meter_boundaries"

    id = Column(Integer, primary_key=True, index=True)
    meter_id = Column(Integer, ForeignKey("meters.id", ondelete="CASCADE"), unique=True, nullable=False)
    boundary_type = Column(String(20), nullable=False)  # GROSS, NET, UNDECLARED, CONFLICTING
    verified_by = Column(String(100), nullable=True)
    documentation_ref = Column(String(255), nullable=True)
    notes = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    meter = relationship("Meter", back_populates="boundary")


class MeterReading(Base):
    __tablename__ = "meter_readings"

    id = Column(Integer, primary_key=True, index=True)
    meter_id = Column(Integer, ForeignKey("meters.id", ondelete="CASCADE"), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    interval_minutes = Column(Integer, default=15)
    power_kw = Column(Float, nullable=True)      # None if missing reading; NEVER zero-filled!
    energy_kwh = Column(Float, nullable=True)
    raw_value = Column(Float, nullable=True)     # Untouched original value for provenance
    is_valid = Column(Boolean, default=True)
    validation_flags = Column(String(100), default="VALID") # VALID, NEGATIVE_SPIKE, MISSING, OUT_OF_BOUNDS, DUPLICATE
    dataset_version_id = Column(Integer, ForeignKey("dataset_versions.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    meter = relationship("Meter", back_populates="readings")


class SolarReading(Base):
    __tablename__ = "solar_readings"

    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False, index=True)
    meter_id = Column(Integer, ForeignKey("meters.id", ondelete="SET NULL"), nullable=True, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    interval_minutes = Column(Integer, default=15)
    generation_kw = Column(Float, nullable=True)  # None if missing reading
    raw_value = Column(Float, nullable=True)
    is_valid = Column(Boolean, default=True)
    dataset_version_id = Column(Integer, ForeignKey("dataset_versions.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    building = relationship("Building", back_populates="solar_readings")
    meter = relationship("Meter", back_populates="solar_readings")


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    versions = relationship("DatasetVersion", back_populates="dataset", cascade="all, delete-orphan")


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"

    id = Column(Integer, primary_key=True, index=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False)
    version_num = Column(Integer, default=1)
    source = Column(String(255), nullable=False) # e.g. "manual_upload", "hackathon_seed", "campus_substation_api"
    file_format = Column(String(20), nullable=False) # CSV, XLSX, JSON
    record_count = Column(Integer, default=0)
    date_range_start = Column(DateTime, nullable=True)
    date_range_end = Column(DateTime, nullable=True)
    columns_json = Column(JSON, nullable=True)
    units = Column(String(50), default="kW, kWh")
    provenance_type = Column(String(50), default="CAMPUS_MEASURED") # CAMPUS_MEASURED, EXTERNAL_VERIFIED
    validation_summary = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    dataset = relationship("Dataset", back_populates="versions")
    imports = relationship("DatasetImport", back_populates="dataset_version", cascade="all, delete-orphan")
    findings = relationship("DataQualityFinding", back_populates="dataset_version")
    decisions = relationship("DSSDecision", back_populates="dataset_version")


class DatasetImport(Base):
    __tablename__ = "dataset_imports"

    id = Column(Integer, primary_key=True, index=True)
    dataset_version_id = Column(Integer, ForeignKey("dataset_versions.id", ondelete="CASCADE"), nullable=False)
    raw_records_count = Column(Integer, default=0)
    valid_records_count = Column(Integer, default=0)
    invalid_records_count = Column(Integer, default=0)
    error_log = Column(JSON, nullable=True)
    imported_at = Column(DateTime, default=utcnow)

    dataset_version = relationship("DatasetVersion", back_populates="imports")


class DataQualityFinding(Base):
    __tablename__ = "data_quality_findings"

    id = Column(Integer, primary_key=True, index=True)
    dataset_version_id = Column(Integer, ForeignKey("dataset_versions.id"), nullable=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="SET NULL"), nullable=True)
    meter_id = Column(Integer, ForeignKey("meters.id", ondelete="SET NULL"), nullable=True)
    issue_category = Column(String(50), nullable=False) # MISSING_INTERVALS, NEGATIVE_VALUES, DUPLICATE_TIMESTAMPS, SOLAR_MISALIGNMENT, BOUNDARY_CONFLICT, IMPLAUSIBLE_SPIKE
    severity = Column(String(20), nullable=False)       # CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL
    validation_rule = Column(String(100), nullable=False)
    explanation = Column(Text, nullable=False)
    recommended_action = Column(Text, nullable=False)
    status = Column(String(20), default="OPEN")         # OPEN, INVESTIGATING, RESOLVED, IGNORED
    created_at = Column(DateTime, default=utcnow)

    building = relationship("Building", back_populates="findings")
    meter = relationship("Meter", back_populates="findings")
    dataset_version = relationship("DatasetVersion", back_populates="findings")


class DSSDecision(Base):
    __tablename__ = "dss_decisions"

    id = Column(Integer, primary_key=True, index=True)
    decision_code = Column(String(50), nullable=False) # RESOLVE_BOUNDARY, AUDIT_REGISTER, RECOMMEND_SUBMETERING, NO_ACTION, INSUFFICIENT_DATA
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False)
    meter_id = Column(Integer, ForeignKey("meters.id", ondelete="SET NULL"), nullable=True)
    dataset_version_id = Column(Integer, ForeignKey("dataset_versions.id"), nullable=True)
    rule_version = Column(String(50), default="DSS-CORE-V1.0")
    evidence_grade = Column(String(10), nullable=False) # E0, E1, E2, E3
    severity = Column(String(20), nullable=False)       # CRITICAL, HIGH, MEDIUM, LOW, INFORMATIONAL
    eligibility = Column(String(30), nullable=False)    # ELIGIBLE, NOT_ELIGIBLE, PENDING_INVESTIGATION, INSUFFICIENT_DATA
    recommended_action = Column(Text, nullable=False)
    human_review_required = Column(Boolean, default=True)
    status = Column(String(30), default="PENDING_REVIEW") # PENDING_REVIEW, APPROVED, REJECTED, MODIFIED, OVERRIDDEN
    created_at = Column(DateTime, default=utcnow)

    building = relationship("Building", back_populates="decisions")
    meter = relationship("Meter", back_populates="decisions")
    dataset_version = relationship("DatasetVersion", back_populates="decisions")
    explanation = relationship("DecisionExplanation", back_populates="decision", uselist=False, cascade="all, delete-orphan")
    recommendation = relationship("Recommendation", back_populates="decision", uselist=False, cascade="all, delete-orphan")
    evidence_records = relationship("EvidenceRecord", back_populates="decision", cascade="all, delete-orphan")
    tasks = relationship("InvestigationTask", back_populates="decision")
    overrides = relationship("ManagementOverride", back_populates="original_decision")
    reviews = relationship("ManagementReview", back_populates="decision")


class DecisionExplanation(Base):
    __tablename__ = "decision_explanations"

    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(Integer, ForeignKey("dss_decisions.id", ondelete="CASCADE"), unique=True, nullable=False)
    what_decided = Column(Text, nullable=False)
    why_decided = Column(Text, nullable=False)
    data_used_json = Column(JSON, nullable=True)
    rule_applied = Column(String(255), nullable=False)
    calculation_details = Column(Text, nullable=True)
    supporting_evidence_json = Column(JSON, nullable=True)
    missing_information = Column(Text, nullable=True)
    uncertainty = Column(Text, nullable=True)
    what_could_change = Column(Text, nullable=True)
    recommended_next_step = Column(Text, nullable=False)
    responsible_role = Column(String(50), nullable=False) # ELECTRICIAN, MANAGEMENT, BOTH
    source_provenance = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=utcnow)

    decision = relationship("DSSDecision", back_populates="explanation")


class Recommendation(Base):
    __tablename__ = "recommendations"

    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(Integer, ForeignKey("dss_decisions.id", ondelete="CASCADE"), unique=True, nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    urgency = Column(String(20), default="MEDIUM") # CRITICAL, HIGH, MEDIUM, LOW
    action_type = Column(String(50), nullable=False)
    status = Column(String(30), default="PENDING_REVIEW") # PENDING_REVIEW, APPROVED, REJECTED, MODIFIED, OVERRIDDEN
    created_at = Column(DateTime, default=utcnow)

    decision = relationship("DSSDecision", back_populates="recommendation")


class EvidenceRecord(Base):
    __tablename__ = "evidence_records"

    id = Column(Integer, primary_key=True, index=True)
    decision_id = Column(Integer, ForeignKey("dss_decisions.id", ondelete="CASCADE"), nullable=False)
    evidence_type = Column(String(50), nullable=False) # METER_READING, BOUNDARY_DOC, SOLAR_LOG, CALIBRATION_CERT, PHYSICAL_INSPECTION
    description = Column(Text, nullable=False)
    raw_data_ref = Column(String(255), nullable=True)
    source_table = Column(String(50), nullable=True)
    source_ids = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    decision = relationship("DSSDecision", back_populates="evidence_records")


class InvestigationTask(Base):
    __tablename__ = "investigation_tasks"

    id = Column(Integer, primary_key=True, index=True)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False)
    meter_id = Column(Integer, ForeignKey("meters.id", ondelete="SET NULL"), nullable=True)
    decision_id = Column(Integer, ForeignKey("dss_decisions.id", ondelete="SET NULL"), nullable=True)
    assigned_to_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    assigned_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    priority = Column(String(20), default="MEDIUM") # CRITICAL, HIGH, MEDIUM, LOW
    status = Column(String(30), default="ASSIGNED") # ASSIGNED, IN_PROGRESS, NEEDS_INFORMATION, SUBMITTED_FOR_REVIEW, COMPLETED, REOPENED
    required_inspection = Column(Text, nullable=False)
    supporting_evidence = Column(Text, nullable=True)
    instructions = Column(Text, nullable=True)
    due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    building = relationship("Building", back_populates="tasks")
    meter = relationship("Meter", back_populates="tasks")
    decision = relationship("DSSDecision", back_populates="tasks")
    assigned_to = relationship("User", foreign_keys=[assigned_to_user_id], back_populates="assigned_tasks")
    assigned_by = relationship("User", foreign_keys=[assigned_by_user_id], back_populates="created_tasks")
    feedback = relationship("ElectricianFeedback", back_populates="task", cascade="all, delete-orphan")


class ElectricianFeedback(Base):
    __tablename__ = "electrician_feedback"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, ForeignKey("investigation_tasks.id", ondelete="SET NULL"), nullable=True)
    decision_id = Column(Integer, ForeignKey("dss_decisions.id", ondelete="SET NULL"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    building_id = Column(Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False)
    meter_id = Column(Integer, ForeignKey("meters.id", ondelete="SET NULL"), nullable=True)
    feedback_category = Column(String(50), nullable=False) # METER_CONFIGURATION, METER_BOUNDARY, SOLAR_MISMATCH, FAULTY_READING, MISSING_READING, TIMESTAMP_ISSUE, EQUIPMENT_OBSERVATION, MAINTENANCE_ISSUE, OTHER
    technical_observation = Column(Text, nullable=False)
    explanation = Column(Text, nullable=False)
    supporting_evidence = Column(Text, nullable=True)
    suggested_correction = Column(Text, nullable=True)
    status = Column(String(30), default="PENDING_REVIEW") # PENDING_REVIEW, ACCEPTED, REJECTED, CLARIFICATION_REQUESTED
    created_at = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="feedback")
    task = relationship("InvestigationTask", back_populates="feedback")
    reviews = relationship("ManagementReview", back_populates="feedback")


class ManagementReview(Base):
    __tablename__ = "management_reviews"

    id = Column(Integer, primary_key=True, index=True)
    feedback_id = Column(Integer, ForeignKey("electrician_feedback.id", ondelete="SET NULL"), nullable=True)
    decision_id = Column(Integer, ForeignKey("dss_decisions.id", ondelete="SET NULL"), nullable=True)
    reviewer_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action = Column(String(30), nullable=False) # APPROVE, REJECT, MODIFY, OVERRIDE, CLARIFICATION_REQUESTED, ACCEPT_FEEDBACK
    reason = Column(Text, nullable=False)       # Mandatory justification
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    feedback = relationship("ElectricianFeedback", back_populates="reviews")
    decision = relationship("DSSDecision", back_populates="reviews")
    reviewer = relationship("User", back_populates="reviews")


class ManagementOverride(Base):
    __tablename__ = "management_overrides"

    id = Column(Integer, primary_key=True, index=True)
    original_decision_id = Column(Integer, ForeignKey("dss_decisions.id", ondelete="CASCADE"), nullable=False)
    reviewer_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    override_decision_code = Column(String(50), nullable=False)
    override_action = Column(Text, nullable=False)
    justification = Column(Text, nullable=False) # Mandatory justification
    preserved_original_snapshot = Column(JSON, nullable=False) # Preserves original DSS decision, grade, severity, explanation
    created_at = Column(DateTime, default=utcnow)

    original_decision = relationship("DSSDecision", back_populates="overrides")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=utcnow, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    role = Column(String(30), nullable=True)
    event_type = Column(String(50), nullable=False) # LOGIN, LOGOUT, FEEDBACK_SUBMITTED, TASK_ASSIGNED, TASK_STATUS_CHANGED, RECOMMENDATION_APPROVED, RECOMMENDATION_REJECTED, RECOMMENDATION_MODIFIED, DECISION_OVERRIDDEN, DATASET_IMPORTED, MODEL_TRAINED, MODEL_APPROVED, MODEL_ROLLED_BACK
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(String(50), nullable=True)
    action_details = Column(JSON, nullable=False)
    ip_address = Column(String(50), default="127.0.0.1")
    is_immutable = Column(Boolean, default=True)

    user = relationship("User", back_populates="audit_events")


class Model(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    task_type = Column(String(50), nullable=False) # PEAK_FORECASTING, ANOMALY_DETECTION, DEMAND_CLUSTERING
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    versions = relationship("ModelVersion", back_populates="model", cascade="all, delete-orphan")


class ModelVersion(Base):
    __tablename__ = "model_versions"

    id = Column(Integer, primary_key=True, index=True)
    model_id = Column(Integer, ForeignKey("models.id", ondelete="CASCADE"), nullable=False)
    version_num = Column(Integer, default=1)
    model_type = Column(String(50), nullable=False) # HISTORICAL_BASELINE, RIDGE_REGRESSION, RANDOM_FOREST, GRADIENT_BOOSTING, ISOLATION_FOREST
    dataset_version_id = Column(Integer, ForeignKey("dataset_versions.id"), nullable=True)
    training_period = Column(String(100), nullable=False)
    test_period = Column(String(100), nullable=False)
    features_used = Column(JSON, nullable=False)
    metrics_json = Column(JSON, nullable=False) # MAE, RMSE, MAPE
    status = Column(String(30), default="TRAINED") # TRAINED, APPROVED, ACTIVE, REJECTED, RETIRED
    limitations = Column(Text, nullable=True)
    model_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow)

    model = relationship("Model", back_populates="versions")
    evaluations = relationship("ModelEvaluation", back_populates="model_version", cascade="all, delete-orphan")


class ModelEvaluation(Base):
    __tablename__ = "model_evaluations"

    id = Column(Integer, primary_key=True, index=True)
    model_version_id = Column(Integer, ForeignKey("model_versions.id", ondelete="CASCADE"), nullable=False)
    mae = Column(Float, nullable=True)
    rmse = Column(Float, nullable=True)
    mape = Column(Float, nullable=True)
    baseline_mae = Column(Float, nullable=True)
    baseline_rmse = Column(Float, nullable=True)
    comparison_summary = Column(Text, nullable=True)
    human_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)

    model_version = relationship("ModelVersion", back_populates="evaluations")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True) # None = broadcast to role
    role = Column(String(30), nullable=True)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    link_url = Column(String(255), nullable=True)
    is_read = Column(Boolean, default=False)
    severity = Column(String(20), default="INFO")
    created_at = Column(DateTime, default=utcnow)


class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(255), nullable=False)
    report_type = Column(String(50), nullable=False) # DAILY_CAMPUS_SUMMARY, PEAK_DEMAND, BUILDING_COMPARISON, DATA_QUALITY, SOLAR_BOUNDARY, EVIDENCE_ASSESSMENT, SEVERITY, RECOMMENDATION, ELECTRICIAN_INVESTIGATION, HUMAN_AI_DECISION, AUDIT
    generated_by_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    parameters_json = Column(JSON, nullable=True)
    file_path = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=utcnow)

