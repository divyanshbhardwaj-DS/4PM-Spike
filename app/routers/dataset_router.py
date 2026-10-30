import io
import json
import zipfile
import datetime
import pandas as pd
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import (
    User, Dataset, DatasetVersion, DatasetImport, Building, Meter,
    MeterReading, SolarReading, DataQualityFinding, DSSDecision, DecisionExplanation, Recommendation
)
from app.auth import get_current_user, require_role, record_audit_event
from app.engines.validation import validate_meter_readings_dataset
from app.engines.dss_engine import run_dss_deterministic_pipeline

router = APIRouter(prefix="/api/datasets", tags=["Dataset Management"])

@router.get("")
def list_datasets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    datasets = db.query(Dataset).all()
    results = []
    for d in datasets:
        versions = db.query(DatasetVersion).filter(DatasetVersion.dataset_id == d.id).order_by(DatasetVersion.version_num.desc()).all()
        results.append({
            "id": d.id,
            "name": d.name,
            "description": d.description,
            "created_at": d.created_at.isoformat(),
            "versions": [
                {
                    "id": v.id,
                    "version_num": v.version_num,
                    "source": v.source,
                    "file_format": v.file_format,
                    "record_count": v.record_count,
                    "provenance_type": v.provenance_type,
                    "date_range_start": v.date_range_start.isoformat() if v.date_range_start else None,
                    "date_range_end": v.date_range_end.isoformat() if v.date_range_end else None,
                    "units": v.units,
                    "validation_summary": v.validation_summary,
                    "created_at": v.created_at.isoformat()
                }
                for v in versions
            ]
        })
    return results

@router.post("/preview")
async def preview_uploaded_dataset(
    file: UploadFile = File(...),
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"]))
):
    """
    Step 3 of import process: Previews columns and sample rows without saving.
    Supports CSV, XLSX, and JSON.
    """
    content = await file.read()
    filename = file.filename or "unknown.csv"

    try:
        if filename.endswith(".csv") or filename.endswith(".txt"):
            df = pd.read_csv(io.BytesIO(content))
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content))
        elif filename.endswith(".json"):
            data = json.loads(content.decode("utf-8"))
            df = pd.DataFrame(data if isinstance(data, list) else data.get("records", []))
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Please upload CSV, XLSX, or JSON.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {str(e)}")

    columns = list(df.columns)
    sample_rows = df.head(5).fillna("").to_dict(orient="records")

    # Suggest canonical mapping
    suggested_mapping = {}
    col_lower = {c.lower(): c for c in columns}

    for target, candidates in [
        ("timestamp", ["timestamp", "time", "datetime", "date", "interval_time", "read_time"]),
        ("power_kw", ["power_kw", "power", "kw", "active_power", "demand_kw", "load_kw"]),
        ("energy_kwh", ["energy_kwh", "energy", "kwh", "consumption"]),
        ("meter_code", ["meter_code", "meter_id", "meter", "device_id"]),
        ("building_code", ["building_code", "building_id", "building", "facility_id"]),
        ("solar_kw", ["solar_kw", "solar", "generation_kw", "pv_kw"])
    ]:
        for cand in candidates:
            if cand in col_lower:
                suggested_mapping[target] = col_lower[cand]
                break

    return {
        "filename": filename,
        "total_rows": len(df),
        "columns": columns,
        "sample_records": sample_rows,
        "suggested_mapping": suggested_mapping
    }

@router.post("/import")
async def import_user_dataset(
    file: UploadFile = File(...),
    dataset_name: str = Form("User Uploaded Campus Dataset"),
    dataset_type: str = Form("METER_READINGS"), # METER_READINGS, BUILDINGS, SOLAR_READINGS
    column_mapping_json: str = Form("{}"),
    provenance_source: str = Form("USER_FILE_UPLOAD"),
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Executes full 14-step deterministic dataset import process:
    Validates schema, checks duplicates, preserves raw values, never zero-fills,
    creates versioned dataset, executes DSS pipeline, records audit event.
    """
    content = await file.read()
    filename = file.filename or "upload.csv"

    # 1. Parse File
    try:
        if filename.endswith(".csv") or filename.endswith(".txt"):
            df = pd.read_csv(io.BytesIO(content))
            file_format = "CSV"
        elif filename.endswith(".xlsx") or filename.endswith(".xls"):
            df = pd.read_excel(io.BytesIO(content))
            file_format = "XLSX"
        elif filename.endswith(".json"):
            data = json.loads(content.decode("utf-8"))
            df = pd.DataFrame(data if isinstance(data, list) else data.get("records", []))
            file_format = "JSON"
        else:
            raise HTTPException(status_code=400, detail="Unsupported format. Upload CSV, XLSX, or JSON.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"File read error: {str(e)}")

    if df.empty:
        raise HTTPException(status_code=400, detail="Uploaded dataset is empty.")

    # 2. Apply Mapping
    try:
        mapping = json.loads(column_mapping_json) if column_mapping_json else {}
    except Exception:
        mapping = {}

    reverse_map = {v: k for k, v in mapping.items() if v in df.columns}
    df = df.rename(columns=reverse_map)

    # 3. Create or Get Dataset
    dataset = db.query(Dataset).filter(Dataset.name == dataset_name).first()
    if not dataset:
        dataset = Dataset(name=dataset_name, description=f"Imported by {current_user.full_name}")
        db.add(dataset)
        db.commit()

    # Get next version number
    latest_v = db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset.id).order_by(DatasetVersion.version_num.desc()).first()
    next_ver = (latest_v.version_num + 1) if latest_v else 1

    dataset_version = DatasetVersion(
        dataset_id=dataset.id,
        version_num=next_ver,
        source=provenance_source,
        file_format=file_format,
        record_count=len(df),
        columns_json=list(df.columns),
        units="kW, kWh",
        provenance_type="CAMPUS_MEASURED",
        validation_summary={"status": "PROCESSING"}
    )
    db.add(dataset_version)
    db.commit()

    # 4. Process Records
    raw_count = len(df)
    valid_count = 0
    invalid_count = 0
    errors = []

    # Check required columns for meter readings
    if "timestamp" not in df.columns or "power_kw" not in df.columns:
        raise HTTPException(
            status_code=400,
            detail="Dataset must contain mapped 'timestamp' and 'power_kw' columns."
        )

    # Find or default building and meter
    b_code = str(df["building_code"].iloc[0]) if "building_code" in df.columns else "BLD-ENG"
    m_code = str(df["meter_code"].iloc[0]) if "meter_code" in df.columns else "MTR-ENG-01"

    building = db.query(Building).filter(Building.code == b_code).first()
    if not building:
        building = Building(name=f"Building {b_code}", code=b_code, category="ACADEMIC", is_protected=False)
        db.add(building)
        db.commit()

    meter = db.query(Meter).filter(Meter.meter_code == m_code).first()
    if not meter:
        meter = Meter(meter_code=m_code, building_id=building.id, boundary_type="GROSS", register_type="MAIN_FEED", unit="kW", status="ACTIVE")
        db.add(meter)
        db.commit()

    # Convert to list of dicts for validation
    records_to_validate = []
    for _, row in df.iterrows():
        records_to_validate.append({
            "timestamp": row.get("timestamp"),
            "power_kw": row.get("power_kw"),
            "energy_kwh": row.get("energy_kwh")
        })

    cleaned_readings, dq_findings, summary = validate_meter_readings_dataset(
        readings=records_to_validate,
        boundary_type=meter.boundary_type,
        meter_code=meter.meter_code,
        building_code=building.code
    )

    min_ts, max_ts = None, None
    for r in cleaned_readings:
        ts = r["timestamp"]
        if ts:
            if min_ts is None or ts < min_ts: min_ts = ts
            if max_ts is None or ts > max_ts: max_ts = ts

        mr = MeterReading(
            meter_id=meter.id,
            timestamp=ts if ts else datetime.datetime.utcnow(),
            interval_minutes=15,
            power_kw=r["power_kw"],
            energy_kwh=r["energy_kwh"],
            raw_value=r["raw_value"],
            is_valid=r["is_valid"],
            validation_flags=r["validation_flags"],
            dataset_version_id=dataset_version.id
        )
        db.add(mr)
        if r["is_valid"]:
            valid_count += 1
        else:
            invalid_count += 1

    # Persist findings
    for f in dq_findings:
        dq_record = DataQualityFinding(
            dataset_version_id=dataset_version.id,
            building_id=building.id,
            meter_id=meter.id,
            issue_category=f["issue_category"],
            severity=f["severity"],
            validation_rule=f["validation_rule"],
            explanation=f["explanation"],
            recommended_action=f["recommended_action"],
            status="OPEN"
        )
        db.add(dq_record)

    # 5. Update Version Details
    dataset_version.date_range_start = min_ts
    dataset_version.date_range_end = max_ts
    dataset_version.validation_summary = {
        "raw_records": raw_count,
        "valid_records": valid_count,
        "invalid_records": invalid_count,
        "quality_findings_count": len(dq_findings),
        "mean_power_kw": summary.get("mean_power_kw"),
        "max_power_kw": summary.get("max_power_kw")
    }

    import_log = DatasetImport(
        dataset_version_id=dataset_version.id,
        raw_records_count=raw_count,
        valid_records_count=valid_count,
        invalid_records_count=invalid_count,
        error_log={"findings": [f["explanation"] for f in dq_findings[:10]]}
    )
    db.add(import_log)
    db.commit()

    # 6. Execute Deterministic DSS Engine Pipeline for the imported data
    target_dates = [min_ts.date()] if min_ts else [datetime.date.today()]
    pipeline_res = run_dss_deterministic_pipeline(
        building_dict={"name": building.name, "code": building.code, "is_protected": building.is_protected},
        meter_dict={"meter_code": meter.meter_code, "boundary_type": meter.boundary_type, "status": meter.status, "register_type": meter.register_type},
        readings=cleaned_readings,
        solar_readings=[],
        target_dates=target_dates,
        historical_baseline_kw=350.0
    )

    decision = DSSDecision(
        decision_code=pipeline_res["decision_code"],
        building_id=building.id,
        meter_id=meter.id,
        dataset_version_id=dataset_version.id,
        rule_version=pipeline_res["rule_version"],
        evidence_grade=pipeline_res["evidence_grade"],
        severity=pipeline_res["severity"],
        eligibility=pipeline_res["eligibility"],
        recommended_action=pipeline_res["recommended_action"],
        human_review_required=pipeline_res["human_review_required"],
        status="PENDING_REVIEW"
    )
    db.add(decision)
    db.commit()

    exp_info = pipeline_res["explanation"]
    explanation = DecisionExplanation(
        decision_id=decision.id,
        what_decided=exp_info["what_decided"],
        why_decided=exp_info["why_decided"],
        data_used_json=exp_info["data_used_json"],
        rule_applied=exp_info["rule_applied"],
        calculation_details=exp_info["calculation_details"],
        supporting_evidence_json=exp_info["supporting_evidence_json"],
        missing_information=exp_info["missing_information"],
        uncertainty=exp_info["uncertainty"],
        what_could_change=exp_info["what_could_change"],
        recommended_next_step=exp_info["recommended_next_step"],
        responsible_role=exp_info["responsible_role"],
        source_provenance=exp_info["source_provenance"]
    )
    db.add(explanation)

    rec = Recommendation(
        decision_id=decision.id,
        title=f"Advisory Action: {pipeline_res['decision_code']} for {building.name}",
        description=pipeline_res["recommended_action"],
        urgency=pipeline_res["severity"],
        action_type=pipeline_res["decision_code"],
        status="PENDING_REVIEW"
    )
    db.add(rec)
    db.commit()

    # 7. Audit Event
    record_audit_event(
        db=db,
        user_id=current_user.id,
        role=current_user.role,
        event_type="DATASET_IMPORTED",
        entity_type="DATASET_VERSION",
        entity_id=str(dataset_version.id),
        action_details={
            "dataset_name": dataset.name,
            "version": next_ver,
            "record_count": raw_count,
            "valid_count": valid_count,
            "decision_code": decision.decision_code
        }
    )

    return {
        "message": "Dataset successfully imported, validated, and evaluated by DSS core engine.",
        "dataset_version_id": dataset_version.id,
        "version_num": next_ver,
        "raw_records": raw_count,
        "valid_records": valid_count,
        "invalid_records": invalid_count,
        "quality_findings_count": len(dq_findings),
        "dss_decision": {
            "id": decision.id,
            "decision_code": decision.decision_code,
            "evidence_grade": decision.evidence_grade,
            "severity": decision.severity,
            "eligibility": decision.eligibility,
            "recommended_action": decision.recommended_action
        }
    }

@router.get("/{version_id}/manifest")
def get_dataset_manifest(
    version_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns official dataset manifest conforming strictly to Section 7.3.
    Excludes sensitive secrets or passwords.
    """
    version = db.query(DatasetVersion).filter(DatasetVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found.")

    dataset = db.query(Dataset).filter(Dataset.id == version.dataset_id).first()
    findings_count = db.query(DataQualityFinding).filter(DataQualityFinding.dataset_version_id == version.id).count()

    return {
        "manifest_version": "DSS-MANIFEST-1.0",
        "dataset_name": dataset.name if dataset else "Unknown",
        "dataset_id": version.dataset_id,
        "version_num": version.version_num,
        "source": version.source,
        "record_count": version.record_count,
        "date_range": {
            "start": version.date_range_start.isoformat() if version.date_range_start else None,
            "end": version.date_range_end.isoformat() if version.date_range_end else None
        },
        "column_definitions": version.columns_json,
        "units": version.units,
        "provenance_classification": version.provenance_type,
        "import_timestamp": version.created_at.isoformat(),
        "validation_status": version.validation_summary,
        "data_quality_findings_total": findings_count
    }

@router.get("/{version_id}/export/{format_type}")
def export_dataset(
    version_id: int,
    format_type: str, # CSV, JSON, XLSX, ZIP
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Exports dataset in CSV, JSON, XLSX, or complete ZIP bundle (with manifest & validation report).
    """
    version = db.query(DatasetVersion).filter(DatasetVersion.id == version_id).first()
    if not version:
        raise HTTPException(status_code=404, detail="Dataset version not found.")

    readings = db.query(MeterReading).filter(MeterReading.dataset_version_id == version.id).all()
    records = [
        {
            "timestamp": r.timestamp.isoformat(),
            "meter_id": r.meter_id,
            "power_kw": r.power_kw,
            "energy_kwh": r.energy_kwh,
            "raw_value": r.raw_value,
            "is_valid": r.is_valid,
            "validation_flags": r.validation_flags
        }
        for r in readings
    ]
    df = pd.DataFrame(records)

    fmt = format_type.upper()
    if fmt == "CSV":
        stream = io.StringIO()
        df.to_csv(stream, index=False)
        return Response(
            content=stream.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=dss_dataset_v{version.version_num}.csv"}
        )

    elif fmt == "JSON":
        return Response(
            content=df.to_json(orient="records", date_format="iso"),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=dss_dataset_v{version.version_num}.json"}
        )

    elif fmt == "XLSX":
        stream = io.BytesIO()
        with pd.ExcelWriter(stream, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="MeterReadings")
        stream.seek(0)
        return Response(
            content=stream.getvalue(),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename=dss_dataset_v{version.version_num}.xlsx"}
        )

    elif fmt == "ZIP":
        # Complete ZIP bundle: CSV readings + Manifest JSON + Validation report JSON
        manifest_data = get_dataset_manifest(version_id, current_user, db)
        findings = db.query(DataQualityFinding).filter(DataQualityFinding.dataset_version_id == version.id).all()
        findings_report = [
            {
                "issue_category": f.issue_category,
                "severity": f.severity,
                "validation_rule": f.validation_rule,
                "explanation": f.explanation,
                "recommended_action": f.recommended_action,
                "status": f.status
            }
            for f in findings
        ]

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
            # 1. Meter readings CSV
            csv_str = df.to_csv(index=False)
            zip_file.writestr(f"readings_v{version.version_num}.csv", csv_str)

            # 2. Manifest JSON
            zip_file.writestr("manifest.json", json.dumps(manifest_data, indent=2))

            # 3. Validation report JSON
            zip_file.writestr("validation_report.json", json.dumps(findings_report, indent=2))

        zip_buffer.seek(0)
        return StreamingResponse(
            zip_buffer,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=dss_bundle_v{version.version_num}.zip"}
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid format. Supported: CSV, JSON, XLSX, ZIP.")

