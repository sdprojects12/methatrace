import datetime
import pandas as pd
import pytest
from utils import report_builder as rb
from utils import sensor_state as ss
from utils.dashboard_data import DashboardData
from utils.integrations import RiskResult
from utils.pipeline_service import attach_observations, flag_threshold, normalize_pipelines


@pytest.fixture
def data(pipelines, observations):
    pl = normalize_pipelines(pipelines)
    obs = flag_threshold(observations)
    obs["is_ml_anomaly"] = [False, True, False, False]
    return DashboardData(pipelines=pl, observations=attach_observations(pl, obs))


def test_inputs_use_selected_pipeline_not_first_row(data):
    state = {}
    ss.set_scenario(state, "P-B", ss.SCENARIO_ANOMALY)
    reading = ss.get_reading(state, "P-B", 8.0)
    inputs = rb.build_report_inputs("P-B", data, reading)
    assert inputs["pipeline"]["pipeline_id"] == "P-B"
    assert inputs["pipeline"]["installation_year"] == 2015 and inputs["pipeline"]["start_coords"] == (18.8, 73.9)
    assert inputs["sensor_readings"]["pressure_bar"] == reading["pressure_bar"]
    assert "Pressure-drop anomaly" in inputs["sensor_readings"]["sensor_status"]
    assert any("Simulated sensor anomaly" in r for r in inputs["recommendations"])
    assert any("Leaking" in r for r in inputs["recommendations"])


def test_inputs_carry_methane_counts_for_that_pipeline(data):
    reading = ss.get_reading({}, "P-A", 70.0)
    inputs = rb.build_report_inputs("P-A", data, reading)
    assert inputs["anomaly_info"]["threshold_anomaly_count"] == 1
    assert inputs["anomaly_info"]["ml_anomaly_count"] == 1
    assert set(inputs["observations_df"]["observation_id"]) == {"O1", "O2"}
    assert inputs["observations_df"].iloc[0]["observation_id"] == "O2"  # flagged rows first
    assert inputs["observations_df"].iloc[0]["is_anomaly"]


def test_quiet_pipeline_and_risk_line(data):
    reading = ss.get_reading({}, "P-B", 8.0)
    recs = rb.build_report_inputs("P-B", data.__class__(pipelines=data.pipelines.assign(status="Active"), observations=data.observations.iloc[0:0]), reading)["recommendations"]
    assert "No anomalies" in recs[0] and recs[-1] == rb.DEMO_NOTE
    risk = RiskResult("ok", "P-A", score=0.4, level="Moderate")
    recs = rb.build_report_inputs("P-A", data, ss.get_reading({}, "P-A", 70.0), risk)["recommendations"]
    assert any("Moderate" in r for r in recs)


def test_unknown_pipeline_raises(data):
    with pytest.raises(ValueError):
        rb.build_report_inputs("nope", data, {})


def test_report_id_is_stable_for_same_state():
    now = datetime.datetime(2026, 11, 3, 9, 0)
    r = {"pressure_bar": 1.0, "flow_rate_m3h": 2.0, "scenario": "Normal"}
    assert rb.make_report_id("P-A", r, now) == rb.make_report_id("P-A", dict(r), now)
    assert rb.make_report_id("P-A", {**r, "pressure_bar": 9}, now) != rb.make_report_id("P-A", r, now)


def test_build_pdf_returns_valid_pdf_with_empty_observations(data):
    reading = ss.get_reading({}, "P-A", 70.0)
    rid, pdf = rb.build_pdf("P-A", data, reading)
    assert rid.startswith("MT-P-A-") and pdf.startswith(b"%PDF") and len(pdf) > 1000
    quiet = data.__class__(pipelines=data.pipelines, observations=data.observations.iloc[0:0])
    assert rb.build_pdf("P-B", quiet, ss.get_reading({}, "P-B", 8.0))[1].startswith(b"%PDF")
