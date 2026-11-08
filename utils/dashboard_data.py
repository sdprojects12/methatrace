"""
Loads and prepares everything the API needs, with graceful degradation.
This module is UI-agnostic: callers decide how to cache and display errors.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from utils import data_loader
from utils.anomaly_detector import detect_ml_anomalies
from utils.pipeline_service import (
    METHANE_THRESHOLD_PPM,
    attach_observations,
    flag_threshold,
    normalize_pipelines,
)

EXPECTED_OBSERVATION_COLUMNS = [
    "observation_id", "timestamp", "latitude", "longitude", "methane_concentration_ppm",
    "wind_speed_kmh", "wind_direction_deg", "source_label", "is_anomaly",
    "is_threshold_anomaly", "is_ml_anomaly", "ml_anomaly_score", "pipeline_id", "distance_m",
]


@dataclass(eq=False)
class DashboardData:
    pipelines: pd.DataFrame = None
    observations: pd.DataFrame = None
    errors: list = field(default_factory=list)      # fatal: the dashboard cannot run
    warnings: list = field(default_factory=list)    # degraded: something is unavailable

    @property
    def ok(self) -> bool:
        return self.pipelines is not None and not self.pipelines.empty

    @property
    def has_observations(self) -> bool:
        return self.observations is not None and not self.observations.empty


def empty_observations() -> pd.DataFrame:
    df = pd.DataFrame({c: pd.Series(dtype="object") for c in EXPECTED_OBSERVATION_COLUMNS})
    for col in ("is_threshold_anomaly", "is_ml_anomaly"):
        df[col] = df[col].astype(bool)
    for col in ("latitude", "longitude", "methane_concentration_ppm", "distance_m"):
        df[col] = df[col].astype(float)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def load_dashboard_data(pipelines_path: str = None, observations_path: str = None) -> DashboardData:
    data = DashboardData(observations=empty_observations())

    # Pipelines (required)
    try:
        data.pipelines = normalize_pipelines(data_loader.read_pipelines(pipelines_path))
        if not data.pipelines["pipeline_id"].is_unique:
            data.warnings.append("Pipeline dataset contains duplicate pipeline_id values; selection may be ambiguous.")
    except data_loader.DataLoadError as e:
        data.errors.append(str(e))
    except Exception as e:  # unexpected failure must not crash the page
        data.errors.append(f"Unexpected error preparing pipeline data: {e}")

    # Observations (optional: methane views degrade gracefully)
    try:
        obs = data_loader.read_observations(observations_path)
    except data_loader.DataLoadError as e:
        data.warnings.append(f"Methane observations unavailable: {e}")
        return data
    except Exception as e:
        data.warnings.append(f"Methane observations unavailable: unexpected error: {e}")
        return data

    obs = flag_threshold(obs)
    if "is_anomaly" in obs.columns:
        mismatch = int((obs["is_anomaly"].fillna(False).astype(bool) != obs["is_threshold_anomaly"]).sum())
        if mismatch:
            data.warnings.append(
                f"The dataset's is_anomaly column disagrees with the {METHANE_THRESHOLD_PPM:g} ppm rule on "
                f"{mismatch} observation(s). The dashboard uses the recomputed threshold flag."
            )

    try:
        obs = detect_ml_anomalies(obs)
    except Exception as e:
        obs["ml_anomaly_score"] = 1
        obs["is_ml_anomaly"] = False
        data.warnings.append(f"ML anomaly detection unavailable ({e}); showing threshold detection only.")

    if data.ok:
        try:
            obs = attach_observations(data.pipelines, obs)
        except Exception as e:
            obs["pipeline_id"] = None
            obs["distance_m"] = float("nan")
            data.warnings.append(f"Could not attribute observations to pipeline segments: {e}")
    else:
        obs["pipeline_id"] = None
        obs["distance_m"] = float("nan")

    data.observations = obs
    return data
