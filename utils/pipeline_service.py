"""
Pure data logic for the MethaTrace dashboard (no Streamlit imports).

Keeps four concepts separate:
  - operational status : asset-register state of a segment (Active, Maintenance, Leaking)
  - methane anomalies  : observation-level detections (ppm threshold, Isolation Forest)
  - sensor anomalies   : simulated pressure/flow deviations (see utils/sensor_state.py)
  - pipeline risk      : computed by the risk engine (see utils/integrations.py)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import geopandas as gpd

# Documented in data/README.md: observations above this value exceed the baseline threshold.
METHANE_THRESHOLD_PPM = 5.0
# Observations farther than this from every pipeline segment are left unattributed.
MATCH_TOLERANCE_M = 250.0
# UTM zone 43N, appropriate for the Chakan / Pune area; used for metre-based distances.
METRIC_CRS = "EPSG:32643"
UNKNOWN = "Unknown"
NORMAL_OPERATIONAL_STATUSES = ("Active",)


def _ensure_crs(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return gdf.set_crs("EPSG:4326") if gdf.crs is None else gdf


def _bool_col(df: pd.DataFrame, col: str) -> pd.Series:
    if col in df.columns:
        return df[col].fillna(False).astype(bool)
    return pd.Series(False, index=df.index)


def _num(value):
    if value is None or pd.isna(value):
        return None
    return float(value)


def line_endpoints(geom):
    """Returns ((lat, lon), (lat, lon)) for a LineString/MultiLineString, else (None, None)."""
    if geom is None or geom.is_empty:
        return None, None
    if geom.geom_type == "LineString":
        first, last = geom.coords[0], geom.coords[-1]
    elif geom.geom_type == "MultiLineString":
        first, last = geom.geoms[0].coords[0], geom.geoms[-1].coords[-1]
    else:
        return None, None
    return (first[1], first[0]), (last[1], last[0])


def normalize_pipelines(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    Returns a copy with guaranteed columns (type, status, material, pressure_bar, depth_m,
    installed, installation_year, length_m). Original columns are preserved so existing
    components such as the map renderer keep working. The input is never modified.
    """
    out = _ensure_crs(gdf.copy()).reset_index(drop=True)

    for col in ("type", "status", "material"):
        if col in out.columns:
            out[col] = out[col].fillna(UNKNOWN).astype(str)
        else:
            out[col] = UNKNOWN
    for col in ("pressure_bar", "depth_m"):
        out[col] = pd.to_numeric(out[col], errors="coerce") if col in out.columns else np.nan

    year_src = next((c for c in ("installation_year", "installed") if c in out.columns), None)
    years = pd.to_numeric(out[year_src], errors="coerce") if year_src else np.nan
    if "installed" not in out.columns:
        out["installed"] = years
    out["installation_year"] = years

    try:
        out["length_m"] = out.to_crs(METRIC_CRS).length.round(1)
    except Exception:
        out["length_m"] = np.nan
    return out


def pipeline_record(pipelines: pd.DataFrame, pipeline_id: str):
    """Returns a plain dict of details for one pipeline, or None if the id is unknown."""
    if pipeline_id is None or pipelines is None or "pipeline_id" not in pipelines.columns:
        return None
    match = pipelines[pipelines["pipeline_id"] == pipeline_id]
    if match.empty:
        return None
    row = match.iloc[0]
    start, end = line_endpoints(row.get("geometry"))
    year = _num(row.get("installation_year"))
    return {
        "pipeline_id": str(row["pipeline_id"]),
        "type": row.get("type", UNKNOWN),
        "status": row.get("status", UNKNOWN),
        "material": row.get("material", UNKNOWN),
        "pressure_bar": _num(row.get("pressure_bar")),
        "depth_m": _num(row.get("depth_m")),
        "installation_year": int(year) if year is not None else None,
        "length_m": _num(row.get("length_m")),
        "start_coords": start,
        "end_coords": end,
    }


def flag_threshold(observations: pd.DataFrame, threshold_ppm: float = METHANE_THRESHOLD_PPM) -> pd.DataFrame:
    """Returns a copy with 'is_threshold_anomaly' (ppm > threshold). The dataset's own
    'is_anomaly' column is left untouched."""
    out = observations.copy()
    out["is_threshold_anomaly"] = out["methane_concentration_ppm"] > threshold_ppm
    return out


def attach_observations(
    pipelines: gpd.GeoDataFrame,
    observations: pd.DataFrame,
    tolerance_m: float = MATCH_TOLERANCE_M,
) -> pd.DataFrame:
    """
    Attributes each observation to the nearest pipeline segment within tolerance_m.
    Adds 'pipeline_id' and 'distance_m' (both missing when no segment is close enough).
    Attribution is spatial proximity only; it does not establish a leak source.
    """
    obs = observations.copy().reset_index(drop=True)
    obs["pipeline_id"] = pd.Series([None] * len(obs), dtype=object)
    obs["distance_m"] = np.nan
    if obs.empty or pipelines is None or len(pipelines) == 0:
        return obs

    valid = obs[["latitude", "longitude"]].notna().all(axis=1)
    if not valid.any():
        return obs

    pts = gpd.GeoDataFrame(
        index=obs.index[valid],
        geometry=gpd.points_from_xy(obs.loc[valid, "longitude"], obs.loc[valid, "latitude"]),
        crs="EPSG:4326",
    ).to_crs(METRIC_CRS)
    lines = _ensure_crs(pipelines)[["pipeline_id", "geometry"]].to_crs(METRIC_CRS)

    joined = gpd.sjoin_nearest(pts, lines, how="left", max_distance=tolerance_m, distance_col="distance_m")
    joined = joined[~joined.index.duplicated(keep="first")]
    matched = joined[joined["pipeline_id"].notna()]
    obs.loc[matched.index, "pipeline_id"] = matched["pipeline_id"].astype(object)
    obs.loc[matched.index, "distance_m"] = matched["distance_m"].round(1)
    return obs


def pipeline_observations(observations: pd.DataFrame, pipeline_id: str) -> pd.DataFrame:
    """Observations attributed to one pipeline, newest first."""
    if observations is None or observations.empty or "pipeline_id" not in observations.columns:
        return observations.iloc[0:0] if observations is not None else pd.DataFrame()
    subset = observations[observations["pipeline_id"] == pipeline_id]
    if "timestamp" in subset.columns:
        subset = subset.sort_values("timestamp", ascending=False)
    return subset


def anomaly_info(observations: pd.DataFrame) -> dict:
    """Counts in the shape utils/pdf_report.generate_report expects."""
    if observations is None or observations.empty:
        return {"threshold_anomaly_count": 0, "ml_anomaly_count": 0, "source_label_counts": {}}
    thr = _bool_col(observations, "is_threshold_anomaly")
    ml = _bool_col(observations, "is_ml_anomaly")
    flagged = observations[thr | ml]
    labels = {}
    if "source_label" in flagged.columns and not flagged.empty:
        labels = {str(k): int(v) for k, v in flagged["source_label"].value_counts().items()}
    return {
        "threshold_anomaly_count": int(thr.sum()),
        "ml_anomaly_count": int(ml.sum()),
        "source_label_counts": labels,
    }


def observation_stats(observations: pd.DataFrame) -> dict:
    """Headline numbers for a set of observations."""
    if observations is None or observations.empty:
        return {"count": 0, "threshold": 0, "ml": 0, "both": 0, "max_ppm": None, "latest": None}
    thr = _bool_col(observations, "is_threshold_anomaly")
    ml = _bool_col(observations, "is_ml_anomaly")
    ts = observations["timestamp"].max() if "timestamp" in observations.columns else None
    return {
        "count": int(len(observations)),
        "threshold": int(thr.sum()),
        "ml": int(ml.sum()),
        "both": int((thr & ml).sum()),
        "max_ppm": float(observations["methane_concentration_ppm"].max()),
        "latest": ts,
    }


def detection_category(observations: pd.DataFrame) -> pd.Series:
    """Per-row label describing which methane detection methods flagged an observation."""
    thr = _bool_col(observations, "is_threshold_anomaly")
    ml = _bool_col(observations, "is_ml_anomaly")
    cat = pd.Series("Not flagged", index=observations.index)
    cat[ml & ~thr] = "ML outlier only"
    cat[thr & ~ml] = "Threshold only"
    cat[thr & ml] = "Threshold and ML"
    return cat


def overview_summary(pipelines: pd.DataFrame, observations: pd.DataFrame) -> dict:
    """Counts for the Overview page. Status counts come from the data, not a fixed list."""
    stats = observation_stats(observations)
    has_obs = observations is not None and not observations.empty
    flagged_ids = set()
    unattributed = 0
    if has_obs and "pipeline_id" in observations.columns:
        flagged = observations[_bool_col(observations, "is_threshold_anomaly") | _bool_col(observations, "is_ml_anomaly")]
        flagged_ids = set(flagged["pipeline_id"].dropna())
        unattributed = int(observations["pipeline_id"].isna().sum())
    return {
        "pipeline_total": int(len(pipelines)) if pipelines is not None else 0,
        "status_counts": {str(k): int(v) for k, v in pipelines["status"].value_counts().items()} if pipelines is not None else {},
        "type_counts": {str(k): int(v) for k, v in pipelines["type"].value_counts().items()} if pipelines is not None else {},
        "observation_total": stats["count"],
        "threshold_anomalies": stats["threshold"],
        "ml_anomalies": stats["ml"],
        "both_methods": stats["both"],
        "segments_with_methane_anomalies": len(flagged_ids),
        "unattributed_observations": unattributed,
    }


def segment_summary(pipelines: pd.DataFrame, observations: pd.DataFrame, sensor_readings: dict = None) -> pd.DataFrame:
    """
    One row per pipeline with the four signals in separate columns:
    operational_status, methane (threshold / ML counts), sensor_alert.
    """
    base = pd.DataFrame(pipelines[["pipeline_id", "type", "status"]]).rename(columns={"status": "operational_status"})
    base = base.reset_index(drop=True)

    has_obs = observations is not None and not observations.empty and "pipeline_id" in observations.columns
    if has_obs:
        obs = observations.dropna(subset=["pipeline_id"]).copy()
        obs["_thr"] = _bool_col(obs, "is_threshold_anomaly")
        obs["_ml"] = _bool_col(obs, "is_ml_anomaly")
        grouped = obs.groupby("pipeline_id").agg(
            observations=("methane_concentration_ppm", "size"),
            max_ppm=("methane_concentration_ppm", "max"),
            threshold_anomalies=("_thr", "sum"),
            ml_outliers=("_ml", "sum"),
        ).reset_index()
        base = base.merge(grouped, on="pipeline_id", how="left")
    for col in ("observations", "threshold_anomalies", "ml_outliers"):
        base[col] = base[col].fillna(0).astype(int) if col in base.columns else 0
    if "max_ppm" not in base.columns:
        base["max_ppm"] = np.nan

    readings = sensor_readings or {}
    base["sensor_alert"] = base["pipeline_id"].map(lambda p: bool(readings.get(p, {}).get("is_anomaly", False)))
    return base[["pipeline_id", "type", "operational_status", "observations", "max_ppm",
                 "threshold_anomalies", "ml_outliers", "sensor_alert"]]


def needs_attention(summary: pd.DataFrame) -> pd.DataFrame:
    """Rows where any of the four signals is non-normal (operational, methane or sensor)."""
    mask = (
        ~summary["operational_status"].isin(NORMAL_OPERATIONAL_STATUSES)
        | (summary["threshold_anomalies"] > 0)
        | (summary["ml_outliers"] > 0)
        | summary["sensor_alert"]
    )
    return summary[mask]
