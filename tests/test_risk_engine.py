import pandas as pd
import pytest
from shapely.geometry import LineString

from utils.risk_engine import calculate_risk_scores


WEATHER = {
    "wind_speed_kmh": 10.0,
    "wind_direction_deg": 270.0,
    "temperature_c": 28.0,
    "source": "test",
}


def pipeline(status="Active", installed=2016, pressure_bar=10.0):
    return pd.DataFrame([{
        "pipeline_id": "P-A",
        "status": status,
        "pressure_bar": pressure_bar,
        "installed": installed,
        "geometry": LineString([(73.805, 18.75), (73.815, 18.75)]),
    }])


def observations(anomaly=False, threshold=False, ppm=9.0):
    return pd.DataFrame([{
        "latitude": 18.75,
        "longitude": 73.805,
        "methane_concentration_ppm": ppm,
        "is_ml_anomaly": anomaly,
        "is_threshold_anomaly": threshold,
    }])


def test_five_component_weights_and_active_baseline():
    result = calculate_risk_scores(
        pipeline(), observations(), weather=WEATHER, reference_year=2026
    ).iloc[0]
    assert result["score_operational"] == 0
    assert result["score_methane"] == 0
    assert result["score_age"] == 5
    assert result["score_pressure"] == 4
    assert result["score_wind"] == 0
    assert result["simulated_risk_score"] == 9
    assert result["risk_level"] == "Low"
    assert result["scored_maximum"] == 100
    assert result["data_quality"] == "complete"


def test_approved_status_examples():
    normal = observations()
    maintenance = calculate_risk_scores(
        pipeline("Maintenance"), normal, weather=WEATHER, reference_year=2026
    ).iloc[0]
    leaking = calculate_risk_scores(
        pipeline("Leaking"), normal, weather=WEATHER, reference_year=2026
    ).iloc[0]
    assert maintenance["simulated_risk_score"] == 24
    assert maintenance["risk_level"] == "Low"
    assert leaking["simulated_risk_score"] == 49
    assert leaking["risk_level"] == "Medium"


def test_active_pipeline_with_multiple_methane_anomalies_is_medium():
    data = pd.concat(
        [observations(anomaly=True, ppm=6.0), observations(threshold=True, ppm=8.0)],
        ignore_index=True,
    )
    result = calculate_risk_scores(
        pipeline(installed=1996, pressure_bar=25.0),
        data,
        weather=WEATHER,
        reference_year=2026,
    ).iloc[0]
    assert result["score_operational"] == 0
    assert result["score_methane"] > 0
    assert result["risk_level"] == "Medium"


def test_ml_and_threshold_only_use_strongest_observation():
    ml = calculate_risk_scores(
        pipeline(), observations(anomaly=True), weather=WEATHER, reference_year=2026
    ).iloc[0]
    threshold = calculate_risk_scores(
        pipeline(), observations(threshold=True), weather=WEATHER, reference_year=2026
    ).iloc[0]
    assert ml["score_methane"] == 21.9
    assert threshold["score_methane"] == 16.4
    assert ml["score_wind"] > threshold["score_wind"]


def test_leaking_with_anomalies_is_high_and_sensor_does_not_affect_score():
    from utils.risk_engine import assess_pipeline_risk

    record = {
        "pipeline_id": "P-A",
        "status": "Leaking",
        "pressure_bar": 25.0,
        "installation_year": 1996,
        "start_coords": (18.75, 73.805),
        "end_coords": (18.75, 73.815),
    }
    data = observations(anomaly=True)
    with_alert = assess_pipeline_risk(
        record, data, sensor_reading={"is_anomaly": True}, weather=WEATHER
    )
    without_alert = assess_pipeline_risk(
        record, data, sensor_reading={"is_anomaly": False}, weather=WEATHER
    )
    assert with_alert["score"] == pytest.approx(92.1, abs=0.1)
    assert with_alert["level"] == "High"
    assert with_alert["score"] == without_alert["score"]
    assert [factor["maximum"] for factor in with_alert["factor_breakdown"]] == [
        40.0, 25.0, 15.0, 10.0, 10.0
    ]


@pytest.mark.parametrize("field", ["status", "installed", "pressure_bar"])
def test_missing_pipeline_component_is_incomplete(field):
    values = {"status": "Active", "installed": 2016, "pressure_bar": 10.0}
    values[field] = None
    result = calculate_risk_scores(
        pipeline(**values), observations(), weather=WEATHER, reference_year=2026
    ).iloc[0]
    assert result["risk_level"] == "Incomplete"
    assert result["data_quality"] == "incomplete"
    assert result["scored_maximum"] < 100
    assert result["simulated_risk_score"] is not None


def test_missing_observations_and_weather_are_incomplete():
    result = calculate_risk_scores(
        pipeline(), None, weather={}, reference_year=2026
    ).iloc[0]
    assert result["score_methane"] is None
    assert result["score_wind"] is None
    assert result["risk_level"] == "Incomplete"
    assert result["scored_maximum"] == 65


def test_no_anomalies_are_an_evaluated_zero():
    result = calculate_risk_scores(
        pipeline(), observations(), weather=WEATHER, reference_year=2026
    ).iloc[0]
    assert bool(result["score_methane_available"]) is True
    assert result["score_methane"] == 0


def test_missing_anomaly_classification_is_unavailable():
    data = observations().drop(columns=["is_ml_anomaly"])
    result = calculate_risk_scores(
        pipeline(), data, weather=WEATHER, reference_year=2026
    ).iloc[0]
    assert result["score_methane"] is None
    assert result["risk_level"] == "Incomplete"
