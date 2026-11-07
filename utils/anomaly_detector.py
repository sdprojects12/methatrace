
import pandas as pd
from sklearn.ensemble import IsolationForest

FEATURES = ["methane_concentration_ppm", "wind_speed_kmh"]
CONTAMINATION = 0.10


def detect_ml_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Detect statistical outliers using Isolation Forest.

    Returns a new DataFrame without modifying the input.
    Rows with missing feature values are not classified as anomalies.
    """

    missing = [col for col in FEATURES if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required features: {missing}")

    result = df.copy()

    result["ml_anomaly_score"] = 1
    result["is_ml_anomaly"] = False

    if result.empty:
        return result

    valid = result[FEATURES].notna().all(axis=1)

    # Isolation Forest needs enough valid observations to fit.
    if valid.sum() < 2:
        return result

    model = IsolationForest(
        n_estimators=100,
        contamination=CONTAMINATION,
        random_state=42,
    )

    predictions = model.fit_predict(result.loc[valid, FEATURES])

    result.loc[valid, "ml_anomaly_score"] = predictions
    result.loc[valid, "is_ml_anomaly"] = predictions == -1

    return result
