import datetime
from typing import Dict, Any, List
from app.config import (
    PEAK_WINDOW_START_HOUR,
    PEAK_WINDOW_END_HOUR,
    INTERVAL_MINUTES,
    EXPECTED_PEAK_INTERVALS_PER_DAY,
    COMPLETENESS_THRESHOLD
)

def generate_expected_peak_intervals(target_date: datetime.date) -> List[datetime.datetime]:
    """
    Generates exact expected interval timestamps for the 16:00 to 20:00 exclusive window.
    15-minute resolution: 16:00, 16:15, 16:30, 16:45, 17:00, 17:15, 17:30, 17:45,
    18:00, 18:15, 18:30, 18:45, 19:00, 19:15, 19:30, 19:45.
    20:00 is strictly EXCLUDED.
    Total: 16 intervals per day.
    """
    intervals = []
    current_dt = datetime.datetime.combine(target_date, datetime.time(PEAK_WINDOW_START_HOUR, 0))
    end_dt = datetime.datetime.combine(target_date, datetime.time(PEAK_WINDOW_END_HOUR, 0))

    while current_dt < end_dt:
        intervals.append(current_dt)
        current_dt += datetime.timedelta(minutes=INTERVAL_MINUTES)
    return intervals

def evaluate_completeness(readings: List[Any], target_dates: List[datetime.date]) -> Dict[str, Any]:
    """
    Evaluates dataset completeness against the deterministic interval schedule.
    Never relies solely on received records count as denominator.
    """
    if not target_dates:
        return {
            "expected_count": 0,
            "received_count": 0,
            "valid_count": 0,
            "missing_count": 0,
            "invalid_count": 0,
            "completeness_pct": 0.0,
            "is_complete": False,
            "missing_timestamps": []
        }

    total_expected_intervals = []
    for d in target_dates:
        total_expected_intervals.extend(generate_expected_peak_intervals(d))

    expected_count = len(total_expected_intervals)
    expected_set = set(total_expected_intervals)

    # Map existing readings by timestamp
    valid_timestamps = set()
    invalid_timestamps = set()

    for r in readings:
        ts = r.timestamp if hasattr(r, 'timestamp') else r.get('timestamp')
        if isinstance(ts, str):
            try:
                ts = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                continue

        # Check if in expected window
        if ts in expected_set:
            is_valid = r.is_valid if hasattr(r, 'is_valid') else r.get('is_valid', True)
            power_val = r.power_kw if hasattr(r, 'power_kw') else r.get('power_kw')

            if is_valid and power_val is not None:
                valid_timestamps.add(ts)
            else:
                invalid_timestamps.add(ts)

    valid_count = len(valid_timestamps)
    invalid_count = len(invalid_timestamps)
    missing_timestamps = sorted(list(expected_set - valid_timestamps))
    missing_count = len(missing_timestamps)

    completeness_pct = round((valid_count / expected_count * 100.0), 2) if expected_count > 0 else 0.0
    is_complete = (completeness_pct >= (COMPLETENESS_THRESHOLD * 100.0))

    return {
        "expected_count": expected_count,
        "valid_count": valid_count,
        "missing_count": missing_count,
        "invalid_count": invalid_count,
        "completeness_pct": completeness_pct,
        "threshold_pct": COMPLETENESS_THRESHOLD * 100.0,
        "is_complete": is_complete,
        "missing_timestamps": [t.isoformat() for t in missing_timestamps]
    }

