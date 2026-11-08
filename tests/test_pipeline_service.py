import numpy as np
import pandas as pd
from utils import pipeline_service as ps


def test_normalize_adds_columns_and_does_not_mutate(pipelines):
    before = list(pipelines.columns)
    out = ps.normalize_pipelines(pipelines)
    assert list(pipelines.columns) == before
    assert {"installation_year", "length_m", "installed"} <= set(out.columns)
    assert out["length_m"].iloc[0] > 900  # ~0.01 degrees of longitude at 18.75N is ~1 km


def test_normalize_handles_missing_optional_columns(pipelines):
    slim = pipelines[["pipeline_id", "status", "geometry"]]
    out = ps.normalize_pipelines(slim)
    assert (out["type"] == ps.UNKNOWN).all()
    assert out["pressure_bar"].isna().all()


def test_pipeline_record_maps_endpoints_and_fields(pipelines):
    rec = ps.pipeline_record(ps.normalize_pipelines(pipelines), "P-B")
    assert rec["status"] == "Leaking"
    assert rec["installation_year"] == 2015
    assert rec["start_coords"] == (18.8, 73.9)  # (lat, lon)
    assert ps.pipeline_record(ps.normalize_pipelines(pipelines), "nope") is None
    assert ps.pipeline_record(ps.normalize_pipelines(pipelines), None) is None


def test_flag_threshold_uses_ppm_rule_and_keeps_dataset_flag(observations):
    out = ps.flag_threshold(observations)
    assert out["is_threshold_anomaly"].tolist() == [False, True, False, False]
    assert out["is_anomaly"].tolist() == observations["is_anomaly"].tolist()
    assert "is_threshold_anomaly" not in observations.columns


def test_attach_observations_nearest_within_tolerance(pipelines, observations):
    out = ps.attach_observations(ps.normalize_pipelines(pipelines), observations)
    assert out["pipeline_id"].tolist()[:3] == ["P-A", "P-A", "P-B"]
    assert pd.isna(out["pipeline_id"].iloc[3])
    assert out["distance_m"].iloc[0] < 50
    assert "pipeline_id" not in observations.columns


def test_attach_observations_respects_tolerance(pipelines, observations):
    out = ps.attach_observations(ps.normalize_pipelines(pipelines), observations, tolerance_m=1)
    assert out["pipeline_id"].isna().all()


def test_attach_observations_empty_inputs(pipelines, observations):
    assert ps.attach_observations(pipelines, observations.iloc[0:0]).empty
    out = ps.attach_observations(pipelines.iloc[0:0], observations)
    assert out["pipeline_id"].isna().all()


def _prepared(pipelines, observations):
    obs = ps.flag_threshold(observations)
    obs["is_ml_anomaly"] = [False, True, False, False]
    return ps.normalize_pipelines(pipelines), ps.attach_observations(ps.normalize_pipelines(pipelines), obs)


def test_overview_summary_counts(pipelines, observations):
    pl, obs = _prepared(pipelines, observations)
    s = ps.overview_summary(pl, obs)
    assert s["pipeline_total"] == 2
    assert s["status_counts"] == {"Active": 1, "Leaking": 1}
    assert (s["threshold_anomalies"], s["ml_anomalies"], s["both_methods"]) == (1, 1, 1)
    assert s["segments_with_methane_anomalies"] == 1
    assert s["unattributed_observations"] == 1


def test_segment_summary_keeps_signals_separate(pipelines, observations):
    pl, obs = _prepared(pipelines, observations)
    summary = ps.segment_summary(pl, obs, {"P-B": {"is_anomaly": True}})
    a = summary[summary.pipeline_id == "P-A"].iloc[0]
    b = summary[summary.pipeline_id == "P-B"].iloc[0]
    assert (a.operational_status, a.threshold_anomalies, a.ml_outliers, a.sensor_alert) == ("Active", 1, 1, False)
    assert (b.operational_status, b.threshold_anomalies, b.sensor_alert) == ("Leaking", 0, True)
    assert set(ps.needs_attention(summary).pipeline_id) == {"P-A", "P-B"}


def test_anomaly_info_and_detection_category(pipelines, observations):
    _, obs = _prepared(pipelines, observations)
    info = ps.anomaly_info(obs)
    assert info == {"threshold_anomaly_count": 1, "ml_anomaly_count": 1, "source_label_counts": {"Pipeline Leak": 1}}
    assert ps.detection_category(obs).tolist() == ["Not flagged", "Threshold and ML", "Not flagged", "Not flagged"]
    assert ps.anomaly_info(None)["threshold_anomaly_count"] == 0


def test_pipeline_observations_filters_and_sorts(pipelines, observations):
    _, obs = _prepared(pipelines, observations)
    sub = ps.pipeline_observations(obs, "P-A")
    assert sub["observation_id"].tolist() == ["O2", "O1"]
    assert ps.pipeline_observations(obs, "missing").empty


def test_risk_observations_uses_radius_not_nearest_owner(pipelines, observations):
    pl = ps.normalize_pipelines(pipelines)
    obs = ps.attach_observations(pl, ps.flag_threshold(observations))
    obs.loc[obs["observation_id"] == "O2", "pipeline_id"] = "P-B"

    selected = ps.risk_observations(pl, obs, "P-A")

    assert "O2" in selected["observation_id"].tolist()
    assert selected["observation_id"].is_unique
    assert selected["risk_distance_m"].max() <= 500
    assert obs.loc[obs["observation_id"] == "O2", "pipeline_id"].iloc[0] == "P-B"


def test_risk_observations_excludes_far_and_invalid_coordinate_rows(pipelines, observations):
    pl = ps.normalize_pipelines(pipelines)
    obs = ps.flag_threshold(observations)
    obs.loc[0, "latitude"] = None
    obs.loc[1, "latitude"] = 20.0

    selected = ps.risk_observations(pl, obs, "P-A")

    assert selected.empty


def test_risk_observations_handles_unavailable_and_invalid_geometry(pipelines, observations):
    pl = ps.normalize_pipelines(pipelines)
    assert ps.risk_observations(pl, None, "P-A") is None
    invalid = pl.copy()
    invalid.loc[0, "geometry"] = None
    assert ps.risk_observations(invalid, observations, "P-A").empty
