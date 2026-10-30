import datetime
from typing import List, Dict, Any, Tuple
from app.config import PEAK_WINDOW_START_HOUR, PEAK_WINDOW_END_HOUR, INTERVAL_MINUTES

def validate_meter_readings_dataset(
    readings: List[Dict[str, Any]],
    boundary_type: str = "GROSS",
    meter_code: str = "MTR-UNKNOWN",
    building_code: str = "BLD-UNKNOWN"
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Validates meter readings against deterministic rules.
    Returns: (cleaned_records, findings, summary)
    Does NOT zero-fill missing readings or silently drop records.
    """
    findings = []
    seen_timestamps = set()
    cleaned_records = []

    valid_count = 0
    duplicate_count = 0
    negative_count = 0
    spike_count = 0
    invalid_ts_count = 0

    values_for_stats = []

    for idx, r in enumerate(readings):
        ts_raw = r.get("timestamp")
        power_raw = r.get("power_kw")
        energy_raw = r.get("energy_kwh")

        # 1. Timestamp validation
        dt = None
        if isinstance(ts_raw, datetime.datetime):
            dt = ts_raw
        elif isinstance(ts_raw, str):
            try:
                dt = datetime.datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                pass

        if dt is None:
            invalid_ts_count += 1
            findings.append({
                "issue_category": "INVALID_TIMESTAMP",
                "severity": "HIGH",
                "validation_rule": "RULE-TS-01: Timestamps must adhere to ISO 8601 formatting",
                "explanation": f"Record #{idx+1} contains unparseable timestamp '{ts_raw}' for meter {meter_code}.",
                "recommended_action": "Verify meter clock synchronization and data logger export format.",
                "status": "OPEN",
                "raw_record": r
            })
            continue

        # Check duplicate timestamps
        if dt in seen_timestamps:
            duplicate_count += 1
            findings.append({
                "issue_category": "DUPLICATE_TIMESTAMPS",
                "severity": "MEDIUM",
                "validation_rule": "RULE-TS-02: Each meter interval timestamp must be unique",
                "explanation": f"Duplicate interval detected at {dt.isoformat()} for meter {meter_code}.",
                "recommended_action": "Audit upstream data ingestion pipeline to prevent redundant polling.",
                "status": "OPEN",
                "raw_record": r
            })
            continue
        seen_timestamps.add(dt)

        # 2. Check 15-min interval alignment
        if dt.minute % INTERVAL_MINUTES != 0 or dt.second != 0:
            findings.append({
                "issue_category": "INTERVAL_ALIGNMENT",
                "severity": "LOW",
                "validation_rule": "RULE-INT-01: Timestamps must align to 15-minute intervals (:00, :15, :30, :45)",
                "explanation": f"Timestamp {dt.isoformat()} has non-standard interval offset.",
                "recommended_action": "Configure meter loggers to synchronize with standard quarter-hour boundaries.",
                "status": "OPEN",
                "raw_record": r
            })

        # 3. Value Validation
        is_valid = True
        flags = []
        power_val = None

        if power_raw is not None and str(power_raw).strip() != "":
            try:
                power_val = float(power_raw)
            except ValueError:
                is_valid = False
                flags.append("NON_NUMERIC")
                findings.append({
                    "issue_category": "CORRUPT_VALUE",
                    "severity": "HIGH",
                    "validation_rule": "RULE-VAL-01: Power readings must be numeric values in kW",
                    "explanation": f"Invalid non-numeric power reading '{power_raw}' at {dt.isoformat()}.",
                    "recommended_action": "Check meter register parsing format.",
                    "status": "OPEN",
                    "raw_record": r
                })

        if power_val is not None:
            # Check negative power on GROSS meter
            if power_val < 0:
                negative_count += 1
                if boundary_type == "GROSS":
                    is_valid = False
                    flags.append("NEGATIVE_ON_GROSS")
                    findings.append({
                        "issue_category": "NEGATIVE_VALUES",
                        "severity": "CRITICAL" if power_val < -50 else "HIGH",
                        "validation_rule": "RULE-BND-01: Gross consumption meters must not report negative power values",
                        "explanation": f"Gross meter {meter_code} reported negative demand ({power_val} kW) at {dt.isoformat()}.",
                        "recommended_action": "Physically inspect meter CT (Current Transformer) polarity, register wiring, and verify whether reverse solar feed occurs.",
                        "status": "OPEN",
                        "raw_record": r
                    })
                else:
                    # In NET meter, negative could indicate net solar export
                    flags.append("NET_EXPORT")

            # Check implausible extreme spike
            if power_val > 5000.0:
                spike_count += 1
                is_valid = False
                flags.append("IMPLAUSIBLE_SPIKE")
                findings.append({
                    "issue_category": "IMPLAUSIBLE_SPIKE",
                    "severity": "HIGH",
                    "validation_rule": "RULE-VAL-02: Campus building readings exceeding 5000 kW require secondary verification",
                    "explanation": f"Anomalously high power reading of {power_val} kW detected at {dt.isoformat()} for meter {meter_code}.",
                    "recommended_action": "Check meter multiplier constant (CT/PT ratio) and investigate for sensor surge.",
                    "status": "OPEN",
                    "raw_record": r
                })

            if is_valid:
                valid_count += 1
                values_for_stats.append(power_val)
        else:
            # Missing reading - never zero-filled!
            is_valid = False
            flags.append("MISSING_READING")

        cleaned_records.append({
            "timestamp": dt,
            "interval_minutes": INTERVAL_MINUTES,
            "power_kw": power_val,
            "energy_kwh": float(energy_raw) if energy_raw is not None and str(energy_raw).strip() != "" else None,
            "raw_value": power_raw,
            "is_valid": is_valid,
            "validation_flags": ",".join(flags) if flags else "VALID"
        })

    summary = {
        "total_records": len(readings),
        "valid_count": valid_count,
        "duplicate_count": duplicate_count,
        "negative_count": negative_count,
        "spike_count": spike_count,
        "invalid_ts_count": invalid_ts_count,
        "mean_power_kw": round(sum(values_for_stats) / len(values_for_stats), 2) if values_for_stats else None,
        "max_power_kw": max(values_for_stats) if values_for_stats else None,
        "min_power_kw": min(values_for_stats) if values_for_stats else None,
    }

    return cleaned_records, findings, summary


def validate_solar_readings_dataset(
    solar_records: List[Dict[str, Any]],
    meter_code: str = "SOLAR-UNKNOWN",
    building_code: str = "BLD-UNKNOWN"
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    """
    Validates solar generation readings.
    Solar generation at night (21:00-05:00) indicates logger error.
    Negative solar generation indicates calibration defect.
    """
    findings = []
    cleaned_records = []
    valid_count = 0
    night_generation_count = 0

    for idx, r in enumerate(solar_records):
        ts_raw = r.get("timestamp")
        gen_raw = r.get("generation_kw")

        dt = None
        if isinstance(ts_raw, datetime.datetime):
            dt = ts_raw
        elif isinstance(ts_raw, str):
            try:
                dt = datetime.datetime.fromisoformat(ts_raw.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                pass

        if dt is None:
            findings.append({
                "issue_category": "INVALID_TIMESTAMP",
                "severity": "MEDIUM",
                "validation_rule": "RULE-SLR-01: Solar timestamps must be valid ISO 8601",
                "explanation": f"Solar log #{idx+1} contains unparseable timestamp '{ts_raw}'.",
                "recommended_action": "Audit solar inverter telemetry export.",
                "status": "OPEN",
                "raw_record": r
            })
            continue

        gen_val = None
        is_valid = True
        if gen_raw is not None and str(gen_raw).strip() != "":
            try:
                gen_val = float(gen_raw)
            except ValueError:
                is_valid = False

        if gen_val is not None:
            if gen_val < 0:
                is_valid = False
                findings.append({
                    "issue_category": "NEGATIVE_VALUES",
                    "severity": "MEDIUM",
                    "validation_rule": "RULE-SLR-02: Solar inverter output cannot be negative",
                    "explanation": f"Negative solar generation {gen_val} kW detected at {dt.isoformat()}.",
                    "recommended_action": "Check inverter standby power measurement versus active generation.",
                    "status": "OPEN",
                    "raw_record": r
                })

            # Check night generation (21:00 to 05:00)
            if (dt.hour >= 21 or dt.hour < 5) and gen_val > 1.0:
                night_generation_count += 1
                findings.append({
                    "issue_category": "IMPLAUSIBLE_SPIKE",
                    "severity": "HIGH",
                    "validation_rule": "RULE-SLR-03: Solar generation must be zero during nocturnal hours (21:00 - 05:00)",
                    "explanation": f"Solar array reported {gen_val} kW output during night at {dt.isoformat()}.",
                    "recommended_action": "Verify inverter clock timezone configuration.",
                    "status": "OPEN",
                    "raw_record": r
                })

            if is_valid:
                valid_count += 1

        cleaned_records.append({
            "timestamp": dt,
            "interval_minutes": INTERVAL_MINUTES,
            "generation_kw": gen_val,
            "raw_value": gen_raw,
            "is_valid": is_valid
        })

    summary = {
        "total_records": len(solar_records),
        "valid_count": valid_count,
        "night_generation_count": night_generation_count
    }
    return cleaned_records, findings, summary

