import pytest
from utils import sensor_state as ss
from utils.sensor_sim import ANOMALY_FLOW_FACTOR, ANOMALY_PRESSURE_FACTOR, generate_sensor_readings


def test_legacy_signature_still_works():
    r = generate_sensor_readings("P-1")
    assert {"pipeline_id", "pressure_bar", "flow_rate_m3h", "sensor_status"} <= set(r)
    assert r["sensor_status"] == "NORMAL" and r["synthetic"] is True
    assert generate_sensor_readings("P-1", True)["sensor_status"].startswith("CRITICAL")


def test_seed_is_reproducible_and_anomaly_degrades_same_baseline():
    n = generate_sensor_readings("P-1", False, seed=7)
    a = generate_sensor_readings("P-1", True, seed=7)
    assert n["pressure_bar"] == generate_sensor_readings("P-1", False, seed=7)["pressure_bar"]
    assert a["pressure_bar"] == pytest.approx(n["pressure_bar"] * ANOMALY_PRESSURE_FACTOR, abs=0.02)
    assert a["flow_rate_m3h"] == pytest.approx(n["flow_rate_m3h"] * ANOMALY_FLOW_FACTOR, abs=0.02)
    assert a["pressure_delta_bar"] < 0 < a["flow_delta_m3h"]
    assert n["pressure_delta_bar"] == 0


def test_rated_pressure_is_respected():
    r = generate_sensor_readings("P-1", seed=3, base_pressure_bar=70.0)
    assert 70 * 0.95 <= r["pressure_bar"] <= 70 * 1.05


def test_readings_are_stable_across_reads():
    state = {}
    first = ss.get_reading(state, "P-1", 50.0)
    for _ in range(5):
        assert ss.get_reading(state, "P-1", 50.0) is first


def test_scenarios_and_regeneration():
    state = {}
    normal = ss.get_reading(state, "P-1", 50.0)
    ss.set_scenario(state, "P-1", ss.SCENARIO_ANOMALY)
    anomaly = ss.get_reading(state, "P-1", 50.0)
    assert anomaly["is_anomaly"] and anomaly["scenario"] == ss.SCENARIO_ANOMALY
    assert anomaly["baseline_pressure_bar"] == normal["baseline_pressure_bar"]
    ss.set_scenario(state, "P-1", ss.SCENARIO_NORMAL)
    assert ss.get_reading(state, "P-1", 50.0)["pressure_bar"] == normal["pressure_bar"]
    ss.regenerate(state, "P-1")
    assert ss.get_reading(state, "P-1", 50.0)["baseline_pressure_bar"] != normal["baseline_pressure_bar"]


def test_invalid_scenario_rejected():
    with pytest.raises(ValueError):
        ss.set_scenario({}, "P-1", "Chaos")


def test_fleet_and_alert_summary(pipelines):
    import utils.pipeline_service as ps
    pl = ps.normalize_pipelines(pipelines)
    state = {}
    ss.set_scenario(state, "P-B", ss.SCENARIO_ANOMALY)
    readings = ss.fleet_readings(state, pl)
    assert set(readings) == {"P-A", "P-B"}
    assert ss.alert_summary(readings) == {"monitored": 2, "alerts": 1, "alert_ids": ["P-B"]}
    ss.reset_all(state)
    assert ss.alert_summary(ss.fleet_readings(state, pl))["alerts"] == 0
