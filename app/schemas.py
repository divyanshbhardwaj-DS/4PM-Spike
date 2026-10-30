import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, EmailStr, Field, ConfigDict

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str
    username: str
    full_name: str
    user_id: int

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    user_id: Optional[int] = None

class UserLogin(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)

class BuildingBase(BaseModel):
    name: str
    code: str
    category: str
    is_protected: bool = False
    safety_notes: Optional[str] = None

class BuildingResponse(BuildingBase):
    id: int
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)

class MeterResponse(BaseModel):
    id: int
    meter_code: str
    building_id: int
    boundary_type: str
    register_type: str
    unit: str
    status: str

    model_config = ConfigDict(from_attributes=True)

class MeterReadingItem(BaseModel):
    timestamp: str
    power_kw: Optional[float] = None
    energy_kwh: Optional[float] = None
    interval_minutes: int = 15

class SolarReadingItem(BaseModel):
    timestamp: str
    generation_kw: Optional[float] = None
    interval_minutes: int = 15

class DecisionExplanationResponse(BaseModel):
    id: int
    decision_id: int
    what_decided: str
    why_decided: str
    data_used_json: Optional[Any] = None
    rule_applied: str
    calculation_details: Optional[str] = None
    supporting_evidence_json: Optional[Any] = None
    missing_information: Optional[str] = None
    uncertainty: Optional[str] = None
    what_could_change: Optional[str] = None
    recommended_next_step: str
    responsible_role: str
    source_provenance: str
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)

class DSSDecisionResponse(BaseModel):
    id: int
    decision_code: str
    building_id: int
    meter_id: Optional[int] = None
    dataset_version_id: Optional[int] = None
    rule_version: str
    evidence_grade: str
    severity: str
    eligibility: str
    recommended_action: str
    human_review_required: bool
    status: str
    created_at: datetime.datetime
    explanation: Optional[DecisionExplanationResponse] = None

    model_config = ConfigDict(from_attributes=True)

class InvestigationTaskCreate(BaseModel):
    building_id: int
    meter_id: Optional[int] = None
    decision_id: Optional[int] = None
    assigned_to_user_id: Optional[int] = None
    priority: str = "MEDIUM"
    required_inspection: str
    instructions: Optional[str] = None
    due_date: Optional[datetime.datetime] = None

class InvestigationTaskUpdate(BaseModel):
    status: str # ASSIGNED, IN_PROGRESS, NEEDS_INFORMATION, SUBMITTED_FOR_REVIEW, COMPLETED, REOPENED
    supporting_evidence: Optional[str] = None
    instructions: Optional[str] = None

class InvestigationTaskResponse(BaseModel):
    id: int
    building_id: int
    meter_id: Optional[int] = None
    decision_id: Optional[int] = None
    assigned_to_user_id: Optional[int] = None
    assigned_by_user_id: Optional[int] = None
    priority: str
    status: str
    required_inspection: str
    supporting_evidence: Optional[str] = None
    instructions: Optional[str] = None
    due_date: Optional[datetime.datetime] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)

class ElectricianFeedbackCreate(BaseModel):
    task_id: Optional[int] = None
    decision_id: Optional[int] = None
    building_id: int
    meter_id: Optional[int] = None
    feedback_category: str
    technical_observation: str
    explanation: str
    supporting_evidence: Optional[str] = None
    suggested_correction: Optional[str] = None

class ElectricianFeedbackResponse(BaseModel):
    id: int
    task_id: Optional[int] = None
    decision_id: Optional[int] = None
    user_id: int
    building_id: int
    meter_id: Optional[int] = None
    feedback_category: str
    technical_observation: str
    explanation: str
    supporting_evidence: Optional[str] = None
    suggested_correction: Optional[str] = None
    status: str
    created_at: datetime.datetime

    model_config = ConfigDict(from_attributes=True)

class ManagementReviewCreate(BaseModel):
    feedback_id: Optional[int] = None
    decision_id: Optional[int] = None
    action: str # APPROVE, REJECT, MODIFY, ACCEPT_FEEDBACK, CLARIFICATION_REQUESTED
    reason: str # Mandatory justification
    notes: Optional[str] = None

class ManagementOverrideCreate(BaseModel):
    original_decision_id: int
    override_decision_code: str
    override_action: str
    justification: str # Mandatory justification

class AuditEventResponse(BaseModel):
    id: int
    timestamp: datetime.datetime
    user_id: Optional[int] = None
    role: Optional[str] = None
    event_type: str
    entity_type: Optional[str] = None
    entity_id: Optional[str] = None
    action_details: Any
    ip_address: str

    model_config = ConfigDict(from_attributes=True)

class DatasetImportRequest(BaseModel):
    dataset_name: str
    dataset_type: str # BUILDINGS, METER_READINGS, SOLAR_READINGS, BOUNDARIES, FULL_BUNDLE
    source: str = "MANUAL_UPLOAD"
    file_format: str = "CSV" # CSV, XLSX, JSON
    column_mapping: Optional[Dict[str, str]] = None

