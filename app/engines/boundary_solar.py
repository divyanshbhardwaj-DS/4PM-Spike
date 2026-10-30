import datetime
from typing import Dict, Any, List, Optional

def analyze_meter_boundary_and_solar(
    boundary_type: str,
    meter_readings: List[Dict[str, Any]],
    solar_readings: List[Dict[str, Any]],
    meter_documentation_ref: Optional[str] = None
) -> Dict[str, Any]:
    """
    Analyzes boundary convention and aligns solar generation if legitimately supported.
    Returns:
    {
        "boundary_type": str,
        "is_boundary_resolved": bool,
        "can_reconstruct_gross": bool,
        "solar_available": bool,
        "solar_aligned": bool,
        "reconstructed_readings": List[Dict],
        "calculation_notes": str,
        "explanation": str
    }
    """
    normalized_boundary = boundary_type.upper() if boundary_type else "UNDECLARED"
    if normalized_boundary not in ["GROSS", "NET", "UNDECLARED", "CONFLICTING"]:
        normalized_boundary = "UNDECLARED"

    solar_map = {}
    for sr in solar_readings:
        ts = sr.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                continue
        gen = sr.get("generation_kw")
        if ts and gen is not None and sr.get("is_valid", True):
            solar_map[ts] = float(gen)

    has_solar = len(solar_map) > 0

    # Alignment check
    aligned_count = 0
    meter_ts_count = 0
    for mr in meter_readings:
        ts = mr.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                continue
        if ts:
            meter_ts_count += 1
            if ts in solar_map:
                aligned_count += 1

    solar_aligned = (aligned_count == meter_ts_count and meter_ts_count > 0) if has_solar else False

    is_boundary_resolved = normalized_boundary in ["GROSS", "NET"]
    can_reconstruct_gross = False
    calculation_notes = ""
    reconstructed_readings = []

    if normalized_boundary == "GROSS":
        can_reconstruct_gross = True
        calculation_notes = (
            "Meter is verified GROSS. Measured power represents total building demand. "
            "Solar generation is captured on a separate circuit and is not deducted from this meter reading."
        )
        for mr in meter_readings:
            ts = mr.get("timestamp")
            if isinstance(ts, str):
                try:
                    ts = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                except Exception:
                    pass
            p_val = mr.get("power_kw")
            reconstructed_readings.append({
                "timestamp": ts,
                "gross_demand_kw": p_val,
                "net_demand_kw": (p_val - solar_map.get(ts, 0.0)) if p_val is not None else None,
                "solar_gen_kw": solar_map.get(ts, 0.0),
                "is_derived": False
            })

    elif normalized_boundary == "NET":
        if has_solar and solar_aligned:
            can_reconstruct_gross = True
            calculation_notes = (
                "Meter is verified NET. Gross demand was mathematically reconstructed as: "
                "Gross Demand = Net Measured Power + Aligned Solar Generation. "
                "Both feeds share synchronized 15-minute interval logging."
            )
            for mr in meter_readings:
                ts = mr.get("timestamp")
                if isinstance(ts, str):
                    try:
                        ts = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
                    except Exception:
                        pass
                p_val = mr.get("power_kw")
                s_val = solar_map.get(ts)
                gross_val = (p_val + s_val) if (p_val is not None and s_val is not None) else None
                reconstructed_readings.append({
                    "timestamp": ts,
                    "gross_demand_kw": gross_val,
                    "net_demand_kw": p_val,
                    "solar_gen_kw": s_val,
                    "is_derived": True
                })
        else:
            can_reconstruct_gross = False
            calculation_notes = (
                "Meter is documented as NET, but corresponding solar generation records are missing or misaligned. "
                "Gross consumption cannot be calculated without verified solar generation data."
            )
            for mr in meter_readings:
                ts = mr.get("timestamp")
                reconstructed_readings.append({
                    "timestamp": ts,
                    "gross_demand_kw": None,
                    "net_demand_kw": mr.get("power_kw"),
                    "solar_gen_kw": None,
                    "is_derived": False
                })

    elif normalized_boundary == "CONFLICTING":
        can_reconstruct_gross = False
        calculation_notes = (
            "Meter documentation and field telemetry exhibit conflicting boundary classifications. "
            "Neither gross nor net demand can be certified until physical substation audit is executed."
        )
        for mr in meter_readings:
            reconstructed_readings.append({
                "timestamp": mr.get("timestamp"),
                "gross_demand_kw": None,
                "net_demand_kw": mr.get("power_kw"),
                "solar_gen_kw": None,
                "is_derived": False
            })

    else:  # UNDECLARED
        can_reconstruct_gross = False
        calculation_notes = (
            "Meter boundary is UNDECLARED in campus registry. "
            "System strictly prohibits guessing meter convention without official electrical documentation."
        )
        for mr in meter_readings:
            reconstructed_readings.append({
                "timestamp": mr.get("timestamp"),
                "gross_demand_kw": None,
                "net_demand_kw": mr.get("power_kw"),
                "solar_gen_kw": None,
                "is_derived": False
            })

    explanation = (
        f"Boundary Status: {normalized_boundary}. "
        f"Verified Documentation: {meter_documentation_ref or 'None provided'}. "
        f"{calculation_notes}"
    )

    return {
        "boundary_type": normalized_boundary,
        "is_boundary_resolved": is_boundary_resolved,
        "can_reconstruct_gross": can_reconstruct_gross,
        "has_solar": has_solar,
        "solar_aligned": solar_aligned,
        "aligned_intervals": aligned_count,
        "total_intervals": meter_ts_count,
        "calculation_notes": calculation_notes,
        "explanation": explanation,
        "reconstructed_readings": reconstructed_readings
    }

