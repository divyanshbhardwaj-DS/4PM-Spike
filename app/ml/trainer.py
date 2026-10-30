import datetime
import os
import joblib
import numpy as np
import pandas as pd
from typing import Dict, Any, List, Tuple
from sklearn.linear_model import Ridge
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error
from app.config import MODELS_DIR

def prepare_time_series_features(df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.Series]:
    """
    Extracts time-aware features without future lookahead:
    - hour of day
    - minute of hour
    - day of week
    - lag_1 (15-min prior)
    - lag_2 (30-min prior)
    - lag_4 (60-min prior)
    - rolling 1-hour mean
    """
    df = df.sort_values("timestamp").copy()
    df["hour"] = df["timestamp"].dt.hour
    df["minute"] = df["timestamp"].dt.minute
    df["dayofweek"] = df["timestamp"].dt.dayofweek

    # Lags
    df["lag_1"] = df["power_kw"].shift(1)
    df["lag_2"] = df["power_kw"].shift(2)
    df["lag_4"] = df["power_kw"].shift(4)
    df["rolling_mean_4"] = df["power_kw"].shift(1).rolling(4, min_periods=1).mean()

    feature_cols = ["hour", "minute", "dayofweek", "lag_1", "lag_2", "lag_4", "rolling_mean_4"]
    df_clean = df.dropna(subset=feature_cols + ["power_kw"])

    X = df_clean[feature_cols]
    y = df_clean["power_kw"]
    return X, y, df_clean

def train_demand_forecast_model(
    readings: List[Dict[str, Any]],
    model_type: str = "RIDGE_REGRESSION",
    split_ratio: float = 0.80
) -> Dict[str, Any]:
    """
    Executes offline time-aware model training:
    1. Chronological 80/20 train/test split.
    2. Trains baseline persistence/seasonal model.
    3. Trains candidate regression model.
    4. Evaluates MAE, RMSE, MAPE on holdout test set.
    """
    df = pd.DataFrame(readings)
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp", "power_kw"]).sort_values("timestamp")

    X, y, df_clean = prepare_time_series_features(df)
    n_samples = len(X)
    if n_samples < 20:
        raise ValueError("Insufficient feature rows after lag generation.")

    split_idx = int(n_samples * split_ratio)
    train_df = df_clean.iloc[:split_idx]
    test_df = df_clean.iloc[split_idx:]

    X_train, y_train = X.iloc[:split_idx], y.iloc[:split_idx]
    X_test, y_test = X.iloc[split_idx:], y.iloc[split_idx:]

    train_period = f"{train_df['timestamp'].min().isoformat()} to {train_df['timestamp'].max().isoformat()}"
    test_period = f"{test_df['timestamp'].min().isoformat()} to {test_df['timestamp'].max().isoformat()}"

    # 1. Baseline Model: Persistence (lag_1)
    baseline_pred = test_df["lag_1"].values
    baseline_mae = float(mean_absolute_error(y_test, baseline_pred))
    baseline_rmse = float(np.sqrt(mean_squared_error(y_test, baseline_pred)))

    # 2. Candidate Model
    if model_type == "RANDOM_FOREST":
        model = RandomForestRegressor(n_estimators=50, max_depth=6, random_state=42)
    else:
        model_type = "RIDGE_REGRESSION"
        model = Ridge(alpha=1.0)

    model.fit(X_train, y_train)
    candidate_pred = model.predict(X_test)

    # 3. Metrics
    mae = float(mean_absolute_error(y_test, candidate_pred))
    rmse = float(np.sqrt(mean_squared_error(y_test, candidate_pred)))

    # Safe MAPE calculation (avoid divide by zero)
    mask = y_test > 1.0
    if np.sum(mask) > 0:
        mape = float(np.mean(np.abs((y_test[mask] - candidate_pred[mask]) / y_test[mask])) * 100.0)
    else:
        mape = 0.0

    # Save model artifact
    timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
    model_filename = f"{model_type.lower()}_{timestamp_str}.joblib"
    model_path = os.path.join(MODELS_DIR, model_filename)
    joblib.dump(model, model_path)

    # Comparison summary
    improvement_pct = round(((baseline_mae - mae) / baseline_mae * 100.0), 2) if baseline_mae > 0 else 0.0
    comparison_summary = (
        f"Candidate {model_type} achieved MAE of {round(mae, 2)} kW vs Baseline MAE of {round(baseline_mae, 2)} kW "
        f"({improvement_pct}% improvement on holdout test set)."
    )

    return {
        "model_type": model_type,
        "model_path": model_path,
        "training_period": train_period,
        "test_period": test_period,
        "features_used": list(X.columns),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "metrics": {
            "mae": round(mae, 2),
            "rmse": round(rmse, 2),
            "mape": round(mape, 2)
        },
        "baseline_metrics": {
            "baseline_mae": round(baseline_mae, 2),
            "baseline_rmse": round(baseline_rmse, 2)
        },
        "comparison_summary": comparison_summary,
        "limitations": "Model trained exclusively on historical local interval telemetry. Does not account for sudden unmetered load changes or grid curtailment."
    }

