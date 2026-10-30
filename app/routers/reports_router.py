import io
import json
import datetime
import pandas as pd
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from app.database import get_db
from app.models import User, Building, Meter, MeterReading, DSSDecision, DataQualityFinding, InvestigationTask, ManagementReview, AuditEvent
from app.auth import get_current_user, require_role
from app.config import RULE_VERSION

router = APIRouter(prefix="/api/reports", tags=["Reports & Exports"])

@router.get("/generate")
def generate_report(
    report_type: str = Query(..., description="PEAK_DEMAND, DAILY_CAMPUS_SUMMARY, DATA_QUALITY, HUMAN_AI_DECISION, AUDIT"),
    format_type: str = Query("CSV", description="CSV, JSON, PDF"),
    current_user: User = Depends(require_role(["MANAGEMENT", "ADMIN"])),
    db: Session = Depends(get_db)
):
    """
    Generates official campus energy and decision report.
    Conforms to Section 19 with provenance, analysis window, and rule version.
    """
    rep_type = report_type.upper()
    fmt = format_type.upper()

    metadata = {
        "report_title": f"DSS-1.0 Campus Intelligence Report: {rep_type}",
        "analysis_window": "16:00 inclusive to 20:00 exclusive (15-min intervals)",
        "generated_by": current_user.full_name,
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "rule_version": RULE_VERSION,
        "provenance": "University Substation Verified Meter Telemetry"
    }

    records = []

    if rep_type == "PEAK_DEMAND":
        decisions = db.query(DSSDecision).all()
        for d in decisions:
            b = db.query(Building).filter(Building.id == d.building_id).first()
            exp = d.explanation
            data_used = exp.data_used_json if exp and exp.data_used_json else {}
            records.append({
                "Building Name": b.name if b else "Unknown",
                "Building Code": b.code if b else "N/A",
                "Protected Status": "PROTECTED" if (b and b.is_protected) else "STANDARD",
                "Peak Demand (kW)": data_used.get("peak_demand_kw", "N/A"),
                "Average Demand (kW)": data_used.get("average_demand_kw", "N/A"),
                "Trend": data_used.get("demand_trend", "N/A"),
                "Spike vs Baseline (%)": data_used.get("spike_vs_baseline_pct", "N/A"),
                "Evidence Grade": d.evidence_grade,
                "Severity": d.severity,
                "Eligibility": d.eligibility,
                "Decision Code": d.decision_code
            })

    elif rep_type == "DATA_QUALITY":
        findings = db.query(DataQualityFinding).all()
        for f in findings:
            b = db.query(Building).filter(Building.id == f.building_id).first()
            m = db.query(Meter).filter(Meter.id == f.meter_id).first()
            records.append({
                "Building": b.name if b else "Unknown",
                "Meter": m.meter_code if m else "Unknown",
                "Issue Category": f.issue_category,
                "Severity": f.severity,
                "Validation Rule": f.validation_rule,
                "Explanation": f.explanation,
                "Recommended Action": f.recommended_action,
                "Status": f.status
            })

    elif rep_type == "HUMAN_AI_DECISION":
        decisions = db.query(DSSDecision).all()
        for d in decisions:
            b = db.query(Building).filter(Building.id == d.building_id).first()
            rev = db.query(ManagementReview).filter(ManagementReview.decision_id == d.id).order_by(ManagementReview.created_at.desc()).first()
            records.append({
                "Building": b.name if b else "Unknown",
                "DSS Decision Code": d.decision_code,
                "DSS Recommendation": d.recommended_action,
                "DSS Severity": d.severity,
                "DSS Status": d.status,
                "Human Action": rev.action if rev else "PENDING_REVIEW",
                "Human Justification": rev.reason if rev else "None"
            })

    else:  # DAILY_CAMPUS_SUMMARY
        buildings = db.query(Building).all()
        for b in buildings:
            d = db.query(DSSDecision).filter(DSSDecision.building_id == b.id).order_by(DSSDecision.created_at.desc()).first()
            records.append({
                "Building": b.name,
                "Category": b.category,
                "Protected": "Yes" if b.is_protected else "No",
                "Decision Code": d.decision_code if d else "N/A",
                "Severity": d.severity if d else "INFORMATIONAL",
                "Evidence Grade": d.evidence_grade if d else "E0",
                "Eligibility": d.eligibility if d else "INSUFFICIENT_DATA"
            })

    df = pd.DataFrame(records)

    if fmt == "CSV":
        stream = io.StringIO()
        stream.write(f"# {metadata['report_title']}\n")
        stream.write(f"# Window: {metadata['analysis_window']} | Generated: {metadata['generated_at']} | Rule: {metadata['rule_version']}\n")
        df.to_csv(stream, index=False)
        return Response(
            content=stream.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=dss_{rep_type.lower()}_report.csv"}
        )

    elif fmt == "JSON":
        res_data = {"metadata": metadata, "records": records}
        return Response(
            content=json.dumps(res_data, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=dss_{rep_type.lower()}_report.json"}
        )

    elif fmt == "PDF":
        pdf_stream = io.BytesIO()
        p = canvas.Canvas(pdf_stream, pagesize=letter)
        width, height = letter

        # Header
        p.setFont("Helvetica-Bold", 16)
        p.drawString(50, height - 50, f"Campus Energy Intelligence: {rep_type}")
        p.setFont("Helvetica", 9)
        p.drawString(50, height - 70, f"Generated: {metadata['generated_at']} by {metadata['generated_by']}")
        p.drawString(50, height - 85, f"Analysis Window: {metadata['analysis_window']} | Rule Version: {metadata['rule_version']}")
        p.setLineWidth(1)
        p.line(50, height - 95, width - 50, height - 95)

        y = height - 120
        p.setFont("Helvetica", 9)

        if not records:
            p.drawString(50, y, "No records found for this report configuration.")
        else:
            for i, r in enumerate(records[:30]): # First 30 rows
                line = " | ".join([f"{k}: {v}" for k, v in list(r.items())[:4]])
                p.drawString(50, y, line[:110])
                y -= 18
                if y < 50:
                    p.showPage()
                    y = height - 50
                    p.setFont("Helvetica", 9)

        p.showPage()
        p.save()
        pdf_stream.seek(0)

        return StreamingResponse(
            pdf_stream,
            media_type="application/pdf",
            headers={"Content-Disposition": f"attachment; filename=dss_{rep_type.lower()}_report.pdf"}
        )

    else:
        raise HTTPException(status_code=400, detail="Invalid format. Supported: CSV, JSON, PDF.")

