from typing import Dict, Any, List
import pandas as pd

def assess_ml_suitability(readings: List[Dict[str, Any]], task_type: str = "PEAK_FORECASTING") -> Dict[str, Any]:
    """
    Evaluates whether an uploaded dataset version is statistically suitable for ML.
    Does not allow training if data is insufficient, trivial, or heavily missing.
    """
    if not readings:
        return {
            "is_suitable": False,
            "reason": "Dataset is empty. Zero readings available.",
            "record_count": 0,
            "valid_count": 0,
            "completeness_pct": 0.0,
            "date_span_days": 0,
            "recommendation": "Import a valid energy dataset with at least 3 days of interval readings."
        }

    df = pd.DataFrame(readings)
    if "timestamp" not in df.columns or "power_kw" not in df.columns:
        return {
            "is_suitable": False,
            "reason": "Missing required timestamp or power_kw columns.",
            "record_count": len(df),
            "valid_count": 0,
            "completeness_pct": 0.0,
            "date_span_days": 0,
            "recommendation": "Ensure data conforms to canonical schema."
        }

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    valid_df = df.dropna(subset=["timestamp", "power_kw"])
    valid_df = valid_df[valid_df["power_kw"].apply(lambda x: isinstance(x, (int, float)) and x >= 0)]

    total_records = len(df)
    valid_records = len(valid_df)
    completeness_pct = round((valid_records / total_records * 100.0), 2) if total_records > 0 else 0.0

    if valid_records < 32:  # Less than 2 full peak windows (16 intervals each)
        return {
            "is_suitable": False,
            "reason": f"Only {valid_records} valid interval readings found. ML forecasting requires at least 32 intervals to establish train/test time splits.",
            "record_count": total_records,
            "valid_count": valid_records,
            "completeness_pct": completeness_pct,
            "date_span_days": 0,
            "recommendation": "Acquire additional time-series data before attempting model training."
        }

    min_date = valid_df["timestamp"].min()
    max_date = valid_df["timestamp"].max()
    date_span_days = (max_date - min_date).days + 1

    if date_span_days < 2:
        return {
            "is_suitable": False,
            "reason": f"Data span is only {date_span_days} day. Time-series forecasting requires multi-day historical patterns.",
            "record_count": total_records,
            "valid_count": valid_records,
            "completeness_pct": completeness_pct,
            "date_span_days": date_span_days,
            "recommendation": "Include at least 2 distinct days of historical data."
        }

    # Variance check
    power_std = valid_df["power_kw"].std()
    if power_std < 0.1:
        return {
            "is_suitable": False,
            "reason": "Zero or near-zero variance in power demand. The series is static.",
            "record_count": total_records,
            "valid_count": valid_records,
            "completeness_pct": completeness_pct,
            "date_span_days": date_span_days,
            "recommendation": "Verify meter sensor readings are actively varying."
        }

    return {
        "is_suitable": True,
        "reason": f"Dataset satisfies ML criteria: {valid_records} valid intervals spanning {date_span_days} days with {completeness_pct}% completeness.",
        "record_count": total_records,
        "valid_count": valid_records,
        "completeness_pct": completeness_pct,
        "date_span_days": date_span_days,
        "min_date": min_date.isoformat(),
        "max_date": max_date.isoformat(),
        "recommendation": "Proceed with baseline model training and time-aware evaluation."
    }

