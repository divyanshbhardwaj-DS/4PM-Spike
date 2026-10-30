import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Building, Meter, MeterReading, SolarReading, DSSDecision
from app.auth import get_current_user, require_role, verify_electrician_building_access
from app.engines.demand import filter_peak_window_readings, compute_demand_metrics
from app.engines.boundary_solar import analyze_meter_boundary_and_solar

router = APIRouter(prefix="/api/energy", tags=["Energy Analytics"])

@router.get("/buildings/{building_id}/metrics")
def get_building_energy_metrics(
    building_id: int,
    target_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
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

    meter = db.query(Meter).filter(Meter.building_id == building_id).first()
    if not meter:
        return {"has_valid_data": False, "message": "No meters registered for this building."}

    # Fetch readings
    m_readings_query = db.query(MeterReading).filter(MeterReading.meter_id == meter.id)
    s_readings_query = db.query(SolarReading).filter(SolarReading.building_id == building_id)

    if target_date:
        try:
            d = datetime.date.fromisoformat(target_date)
            start_dt = datetime.datetime.combine(d, datetime.time(0, 0))
            end_dt = datetime.datetime.combine(d, datetime.time(23, 59, 59))
            m_readings_query = m_readings_query.filter(MeterReading.timestamp >= start_dt, MeterReading.timestamp <= end_dt)
            s_readings_query = s_readings_query.filter(SolarReading.timestamp >= start_dt, SolarReading.timestamp <= end_dt)
        except Exception:
            pass

    m_readings = [
        {"timestamp": r.timestamp, "power_kw": r.power_kw, "energy_kwh": r.energy_kwh, "is_valid": r.is_valid}
        for r in m_readings_query.all()
    ]
    s_readings = [
        {"timestamp": s.timestamp, "generation_kw": s.generation_kw, "is_valid": s.is_valid}
        for s in s_readings_query.all()
    ]

    boundary_analysis = analyze_meter_boundary_and_solar(
        boundary_type=meter.boundary_type,
        meter_readings=m_readings,
        solar_readings=s_readings
    )

    peak_readings = filter_peak_window_readings(boundary_analysis.get("reconstructed_readings") or m_readings)

    baseline = 380.0 if building.code == "BLD-ENG" else (600.0 if building.code == "BLD-DC" else (320.0 if building.code == "BLD-SCI" else 200.0))
    demand_metrics = compute_demand_metrics(
        peak_window_readings=peak_readings,
        historical_baseline_kw=baseline
    )

    return {
        "building_id": building.id,
        "building_name": building.name,
        "building_code": building.code,
        "is_protected": building.is_protected,
        "meter_code": meter.meter_code,
        "boundary_analysis": {
            "boundary_type": boundary_analysis["boundary_type"],
            "can_reconstruct_gross": boundary_analysis["can_reconstruct_gross"],
            "has_solar": boundary_analysis["has_solar"],
            "solar_aligned": boundary_analysis["solar_aligned"],
            "explanation": boundary_analysis["explanation"]
        },
        "demand_metrics": demand_metrics,
        "analysis_window": "16:00 to 20:00 (15-min intervals, 20:00 excluded)"
    }

@router.get("/buildings/{building_id}/intervals")
def get_building_intervals(
    building_id: int,
    peak_only: bool = Query(True, description="Filter strictly to 16:00-20:00 window"),
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

    meter = db.query(Meter).filter(Meter.building_id == building_id).first()
    if not meter:
        return []

    m_readings = db.query(MeterReading).filter(
        MeterReading.meter_id == meter.id
    ).order_by(MeterReading.timestamp.asc()).all()

    s_readings = db.query(SolarReading).filter(
        SolarReading.building_id == building_id
    ).all()

    solar_map = {s.timestamp: s.generation_kw for s in s_readings if s.is_valid and s.generation_kw is not None}

    results = []
    for r in m_readings:
        if peak_only and not (16 <= r.timestamp.hour < 20):
            continue

        results.append({
            "timestamp": r.timestamp.isoformat(),
            "power_kw": r.power_kw,
            "solar_kw": solar_map.get(r.timestamp, 0.0),
            "is_valid": r.is_valid,
            "validation_flags": r.validation_flags
        })

    return results

@router.get("/campus-overview")
def get_campus_peak_overview(
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Campus-wide peak demand summary across all buildings during 16:00-20:00.
    Available strictly to Management and Admin personas.
    """
    buildings = db.query(Building).all()
    overview_list = []
    total_peak_kw = 0.0
    highest_spike_building = None
    highest_spike_pct = -100.0

    for b in buildings:
        meter = db.query(Meter).filter(Meter.building_id == b.id).first()
        if not meter:
            continue

        m_readings = [
            {"timestamp": r.timestamp, "power_kw": r.power_kw, "is_valid": r.is_valid}
            for r in db.query(MeterReading).filter(MeterReading.meter_id == meter.id).all()
        ]
        s_readings = [
            {"timestamp": s.timestamp, "generation_kw": s.generation_kw, "is_valid": s.is_valid}
            for s in db.query(SolarReading).filter(SolarReading.building_id == b.id).all()
        ]

        b_analysis = analyze_meter_boundary_and_solar(meter.boundary_type, m_readings, s_readings)
        peak_records = filter_peak_window_readings(b_analysis.get("reconstructed_readings") or m_readings)

        baseline = 380.0 if b.code == "BLD-ENG" else (600.0 if b.code == "BLD-DC" else (320.0 if b.code == "BLD-SCI" else 200.0))
        d_metrics = compute_demand_metrics(peak_records, historical_baseline_kw=baseline)

        latest_dec = db.query(DSSDecision).filter(DSSDecision.building_id == b.id).order_by(DSSDecision.created_at.desc()).first()

        peak_kw = d_metrics.get("peak_demand_kw") or 0.0
        total_peak_kw += peak_kw

        spike_pct = d_metrics.get("spike_vs_baseline_pct")
        if spike_pct and spike_pct > highest_spike_pct:
            highest_spike_pct = spike_pct
            highest_spike_building = b.name

        overview_list.append({
            "building_id": b.id,
            "building_name": b.name,
            "building_code": b.code,
            "category": b.category,
            "is_protected": b.is_protected,
            "boundary_type": meter.boundary_type,
            "peak_demand_kw": peak_kw,
            "average_demand_kw": d_metrics.get("average_demand_kw"),
            "demand_trend": d_metrics.get("demand_trend"),
            "spike_vs_baseline_pct": spike_pct,
            "evidence_grade": latest_dec.evidence_grade if latest_dec else "E0",
            "severity": latest_dec.severity if latest_dec else "INFORMATIONAL",
            "eligibility": latest_dec.eligibility if latest_dec else "INSUFFICIENT_DATA",
            "decision_code": latest_dec.decision_code if latest_dec else "NO_ACTION"
        })

    # Sort by peak demand descending
    overview_list.sort(key=lambda x: x["peak_demand_kw"] or 0, reverse=True)

    return {
        "analysis_window": "16:00 to 20:00 (15-min intervals, 20:00 excluded)",
        "total_campus_peak_kw": round(total_peak_kw, 2),
        "building_count": len(buildings),
        "highest_spike_building": highest_spike_building,
        "highest_spike_pct": highest_spike_pct if highest_spike_building else None,
        "buildings": overview_list
    }

