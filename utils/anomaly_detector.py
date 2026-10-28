import pandas as pd
from sklearn.ensemble import IsolationForest

def detect_ml_anomalies(df: pd.DataFrame) -> pd.DataFrame:
    """
    Applies Machine Learning (Isolation Forest) to detect complex methane anomalies
    based on concentration and wind patterns, replacing static thresholds.
    """
    print("Running ML Anomaly Detection...")
    
    # Features to analyze
    features = ['methane_concentration_ppm', 'wind_speed_kmh']
    
    # Initialize the model (Assumes ~10% of the zone has active leak signatures)
    model = IsolationForest(n_estimators=100, contamination=0.10, random_state=42)
    
    # Fit and predict (-1 is anomaly, 1 is normal)
    df['ml_anomaly_score'] = model.fit_predict(df[features])
    
    # Convert to a clean boolean for the Streamlit map
    df['is_ml_anomaly'] = df['ml_anomaly_score'] == -1
    
    print(f"-> Detected {df['is_ml_anomaly'].sum()} ML-verified emission hotspots.")
    return df