import pandas as pd
import pytest
from utils.anomaly_detector import detect_ml_anomalies
from utils.dashboard_data import load_dashboard_data
from utils.data_loader import DataLoadError, read_observations, read_pipelines


def test_real_datasets_load_with_all_derived_columns():
    d = load_dashboard_data()
    assert d.ok and d.has_observations and not d.errors
    assert {"is_threshold_anomaly", "is_ml_anomaly", "pipeline_id", "distance_m"} <= set(d.observations.columns)
    assert d.pipelines["pipeline_id"].is_unique


def test_missing_files_degrade_without_raising(tmp_path):
    d = load_dashboard_data(str(tmp_path / "no.geojson"), str(tmp_path / "no.csv"))
    assert not d.ok and d.errors and d.warnings
    assert d.observations.empty and "is_ml_anomaly" in d.observations.columns


def test_missing_observations_keeps_pipelines(tmp_path):
    d = load_dashboard_data(None, str(tmp_path / "no.csv"))
    assert d.ok and not d.has_observations
    assert any("Methane observations unavailable" in w for w in d.warnings)


def test_corrupt_files_are_reported(tmp_path):
    bad_geo = tmp_path / "bad.geojson"
    bad_geo.write_text("not json")
    bad_csv = tmp_path / "bad.csv"
    bad_csv.write_text("a,b\n1,2\n")
    d = load_dashboard_data(str(bad_geo), str(bad_csv))
    assert not d.ok and d.errors
    assert any("missing required columns" in w for w in d.warnings)


def test_readers_raise_clear_errors(tmp_path):
    with pytest.raises(DataLoadError, match="not found"):
        read_pipelines(str(tmp_path / "x.geojson"))
    empty = tmp_path / "empty.csv"
    empty.write_text("timestamp,latitude,longitude,methane_concentration_ppm\n")
    with pytest.raises(DataLoadError, match="empty"):
        read_observations(str(empty))


def test_ml_detector_does_not_mutate_and_handles_edge_cases(observations):
    before = observations.copy()
    out = detect_ml_anomalies(observations)
    pd.testing.assert_frame_equal(observations, before)
    assert "is_ml_anomaly" in out.columns and "is_ml_anomaly" not in observations.columns

    assert detect_ml_anomalies(observations.iloc[0:0])["is_ml_anomaly"].sum() == 0
    with_nan = observations.copy()
    with_nan.loc[0, "wind_speed_kmh"] = float("nan")
    assert not detect_ml_anomalies(with_nan).loc[0, "is_ml_anomaly"]
    with pytest.raises(ValueError):
        detect_ml_anomalies(observations.drop(columns=["wind_speed_kmh"]))
