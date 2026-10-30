import datetime
from typing import List, Dict, Any, Optional
from app.config import PEAK_WINDOW_START_HOUR, PEAK_WINDOW_END_HOUR, INTERVAL_MINUTES

def filter_peak_window_readings(readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Filters readings strictly into the primary analysis demand window:
    16:00 inclusive to 20:00 exclusive.
    The reading starting at 20:00:00 is strictly EXCLUDED.
    """
    peak_readings = []
    for r in readings:
        ts = r.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=None)
            except Exception:
                continue
        if not ts:
            continue

        # Check hour range: 16 <= hour < 20
        # 16:00 to 19:45
        if PEAK_WINDOW_START_HOUR <= ts.hour < PEAK_WINDOW_END_HOUR:
            r_copy = r.copy()
            r_copy["timestamp"] = ts
            peak_readings.append(r_copy)
    return sorted(peak_readings, key=lambda x: x["timestamp"])


def compute_demand_metrics(
    peak_window_readings: List[Dict[str, Any]],
    historical_baseline_kw: Optional[float] = None
) -> Dict[str, Any]:
    """
    Computes deterministic demand metrics for the peak window:
    Peak kW, Mean kW, Min kW, Max kW, Trend, Percentile spike vs baseline.
    Never assumes higher demand automatically implies energy wastage.
    """
    valid_power_values = []
    interval_series = []

    for r in peak_window_readings:
        ts = r.get("timestamp")
        power_kw = r.get("gross_demand_kw") if "gross_demand_kw" in r else r.get("power_kw")

        if power_kw is not None and r.get("is_valid", True):
            valid_power_values.append(float(power_kw))
            interval_series.append({
                "timestamp": ts.isoformat() if isinstance(ts, datetime.datetime) else str(ts),
                "power_kw": float(power_kw),
                "solar_kw": r.get("solar_gen_kw", 0.0),
                "net_kw": r.get("net_demand_kw")
            })

    if not valid_power_values:
        return {
            "has_valid_data": False,
            "peak_demand_kw": None,
            "peak_timestamp": None,
            "average_demand_kw": None,
            "min_demand_kw": None,
            "max_demand_kw": None,
            "demand_trend": "UNKNOWN",
            "spike_vs_baseline_pct": None,
            "interval_series": []
        }

    max_kw = max(valid_power_values)
    min_kw = min(valid_power_values)
    avg_kw = round(sum(valid_power_values) / len(valid_power_values), 2)

    # Find peak timestamp
    peak_ts = None
    for item in interval_series:
        if item["power_kw"] == max_kw:
            peak_ts = item["timestamp"]
            break

    # Trend calculation (first half vs second half or start vs end)
    if len(valid_power_values) >= 4:
        start_avg = sum(valid_power_values[:2]) / 2.0
        end_avg = sum(valid_power_values[-2:]) / 2.0
        if end_avg > start_avg * 1.10:
            trend = "RISING"
        elif end_avg < start_avg * 0.90:
            trend = "FALLING"
        else:
            trend = "STABLE"
    else:
        trend = "INSUFFICIENT_INTERVALS"

    spike_pct = None
    if historical_baseline_kw and historical_baseline_kw > 0:
        spike_pct = round(((max_kw - historical_baseline_kw) / historical_baseline_kw) * 100.0, 2)

    return {
        "has_valid_data": True,
        "peak_demand_kw": round(max_kw, 2),
        "peak_timestamp": peak_ts,
        "average_demand_kw": avg_kw,
        "min_demand_kw": round(min_kw, 2),
        "max_demand_kw": round(max_kw, 2),
        "demand_trend": trend,
        "spike_vs_baseline_pct": spike_pct,
        "historical_baseline_kw": historical_baseline_kw,
        "sample_count": len(valid_power_values),
        "interval_series": interval_series
    }

