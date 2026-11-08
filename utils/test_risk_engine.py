"""
Minimal tests for utils/risk_engine.py

Run from the repo root with either:
    python -m pytest tests/test_risk_engine.py -v
    python tests/test_risk_engine.py          (no pytest needed)

No internet and no geopandas are needed: the weather API is mocked and the
pipeline "geometry" is a tiny stand-in class with a .coords attribute (which is
all the risk engine reads from a shapely LineString).
"""

import io
import json
import math
import os
import sys
import urllib.error
from unittest import mock

import pandas as pd

# Make `utils` importable no matter where the tests are launched from
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import risk_engine as re_  # noqa: E402

REF_YEAR = 2026  # fixed so "pipeline age" never changes between runs


# ----------------------------------------------------------------------------
# Test helpers
# ----------------------------------------------------------------------------
class FakeLine:
    """Stand-in for a shapely LineString (the engine only reads .coords)."""
    def __init__(self, coords):
        self.coords = coords


def metres_east_to_deg_lon(metres):
    """Inverse of the engine's flat-earth conversion at Chakan's latitude."""
    return metres / (111_320.0 * math.cos(math.radians(re_.CHAKAN_LAT)))


def make_pipelines(installed=1996, pressure=25.0):
    """One north-south pipeline running through Chakan's centre point."""
    return pd.DataFrame([{
        "pipeline_id": "TRUNK-001",
        "status": "Active",
        "geometry": FakeLine([(re_.CHAKAN_LON, 18.74), (re_.CHAKAN_LON, 18.76)]),
        "pressure_bar": pressure,
        "installed": installed,
    }])


def make_obs(ppm=8.0, metres_east=200.0, ml_flag=True):
    """One methane reading `metres_east` metres EAST of the pipeline."""
    return pd.DataFrame([{
        "latitude": 18.75,
        "longitude": re_.CHAKAN_LON + metres_east_to_deg_lon(metres_east),
        "methane_concentration_ppm": ppm,
        "is_ml_anomaly": ml_flag,
        "is_threshold_anomaly": ppm > 5.0,
    }])


def weather(from_deg):
    return {"wind_speed_kmh": 12.0, "wind_direction_deg": from_deg,
            "temperature_c": 30.0, "source": "test"}


class FakeResponse(io.BytesIO):
    """Mimics the object returned by urllib.request.urlopen (a context manager)."""
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


# ----------------------------------------------------------------------------
# Weather tests
# ----------------------------------------------------------------------------
def test_weather_success_parses_open_meteo_response():
    re_._clear_weather_cache()
    body = json.dumps({"current": {"temperature_2m": 31.5,
                                   "wind_speed_10m": 14.2,
                                   "wind_direction_10m": 225}}).encode()
    with mock.patch.object(re_.urllib.request, "urlopen",
                           return_value=FakeResponse(body)):
        w = re_.fetch_current_weather()
    assert w["source"] == "open-meteo"
    assert w["wind_speed_kmh"] == 14.2
    assert w["wind_direction_deg"] == 225
    assert w["temperature_c"] == 31.5


def test_weather_falls_back_when_network_fails():
    re_._clear_weather_cache()
    with mock.patch.object(re_.urllib.request, "urlopen",
                           side_effect=urllib.error.URLError("no internet")):
        w = re_.fetch_current_weather()  # must NOT raise
    assert w["source"] == "fallback_mock"
    assert w["wind_speed_kmh"] == re_.FALLBACK_WEATHER["wind_speed_kmh"]
    assert w["wind_direction_deg"] == re_.FALLBACK_WEATHER["wind_direction_deg"]


def test_weather_falls_back_on_garbage_response():
    re_._clear_weather_cache()
    # Valid JSON, but missing the "current" block
    with mock.patch.object(re_.urllib.request, "urlopen",
                           return_value=FakeResponse(b'{"oops": 1}')):
        assert re_.fetch_current_weather()["source"] == "fallback_mock"


def test_weather_reuses_last_live_result_after_rate_limit():
    re_._clear_weather_cache()
    body = json.dumps({"current": {"temperature_2m": 31.5,
                                   "wind_speed_10m": 14.2,
                                   "wind_direction_10m": 225}}).encode()
    with mock.patch.object(re_.urllib.request, "urlopen",
                           side_effect=[FakeResponse(body), urllib.error.HTTPError(
                               "https://api.open-meteo.com", 429, "Too Many Requests", {}, None)]) as request:
        fresh = re_.fetch_current_weather()
        stale = re_.fetch_current_weather()
        cooled = re_.fetch_current_weather()
    assert fresh["source"] == "open-meteo"
    assert stale["source"] == "open-meteo"
    assert stale["wind_speed_kmh"] == fresh["wind_speed_kmh"]
    assert "reusing last successful" in stale["note"]
    assert cooled["source"] == "open-meteo"
    assert request.call_count == 2
    # Not JSON at all
    with mock.patch.object(re_.urllib.request, "urlopen",
                           return_value=FakeResponse(b"<html>502</html>")):
        assert re_.fetch_current_weather()["source"] == "fallback_mock"


# ----------------------------------------------------------------------------
# Scoring tests
# ----------------------------------------------------------------------------
def test_exact_score_matches_hand_calculation():
    """
    8.0 PPM, 200 m away, wind blowing FROM the west (270) so the reading
    (east of the pipeline) is downwind:
        methane  = 25 * ((8-2)/8) * (1 - 200/500) = 11.25
        age      = 15 (installed 1996, 30 yrs at 2026)
        pressure = 10 (25 bar)
        wind     = 10 * 1.0 * 0.45 = 4.5
        total    = 40.75  -> "Medium"
    """
    out = re_.calculate_risk_scores(make_pipelines(), make_obs(),
                                    weather=weather(270), reference_year=REF_YEAR)
    row = out.iloc[0]
    assert abs(row["score_methane"] - 11.25) < 0.3
    assert row["score_age"] == 15.0
    assert row["score_pressure"] == 10.0
    assert abs(row["score_wind"] - 4.5) < 0.2
    assert abs(row["simulated_risk_score"] - 40.75) < 0.5
    assert row["risk_level"] == "Medium"


def test_downwind_scores_higher_than_upwind():
    down = re_.calculate_risk_scores(make_pipelines(), make_obs(),
                                     weather=weather(270), reference_year=REF_YEAR)
    up = re_.calculate_risk_scores(make_pipelines(), make_obs(),
                                   weather=weather(90), reference_year=REF_YEAR)
    assert down.iloc[0]["simulated_risk_score"] > up.iloc[0]["simulated_risk_score"]
    assert "downwind" in down.iloc[0]["risk_explanation"]
    assert "upwind" in up.iloc[0]["risk_explanation"]


def test_closer_and_higher_ppm_scores_higher():
    base = re_.calculate_risk_scores(make_pipelines(), make_obs(ppm=5, metres_east=400),
                                     weather=weather(270), reference_year=REF_YEAR)
    worse = re_.calculate_risk_scores(make_pipelines(), make_obs(ppm=9, metres_east=100),
                                      weather=weather(270), reference_year=REF_YEAR)
    assert worse.iloc[0]["simulated_risk_score"] > base.iloc[0]["simulated_risk_score"]


def test_no_methane_means_only_age_and_pressure_count():
    far = make_obs(ppm=9.0, metres_east=5000)  # outside the 500 m search radius
    out = re_.calculate_risk_scores(make_pipelines(installed=2016, pressure=12.5),
                                    far, weather=weather(270), reference_year=REF_YEAR)
    row = out.iloc[0]
    assert row["score_methane"] == 0 and row["score_wind"] == 0
    # age: 10/30*15 = 5.0 ; pressure: 12.5/25*10 = 5.0
    assert abs(row["simulated_risk_score"] - 10.0) < 0.2
    assert row["risk_level"] == "Low"
    assert "no usable methane anomaly" in row["risk_explanation"]


def test_non_ml_anomaly_readings_are_ignored():
    out = re_.calculate_risk_scores(make_pipelines(), make_obs(ml_flag=False),
                                    weather=weather(270), reference_year=REF_YEAR)
    assert out.iloc[0]["score_methane"] > 0


def test_score_always_between_0_and_100_and_explanation_present():
    out = re_.calculate_risk_scores(make_pipelines(installed=1900, pressure=999),
                                    make_obs(ppm=500, metres_east=0),
                                    weather=weather(270), reference_year=REF_YEAR)
    row = out.iloc[0]
    assert 0 <= row["simulated_risk_score"] <= 100
    assert "Simulated" in row["risk_explanation"]
    assert "PPM" in row["risk_explanation"]


def test_missing_install_year_does_not_crash():
    out = re_.calculate_risk_scores(make_pipelines(installed=float("nan")), make_obs(),
                                    weather=weather(270), reference_year=REF_YEAR)
    assert "install year unavailable" in out.iloc[0]["risk_explanation"]


def test_original_dataframe_untouched_and_disclaimer_attached():
    pipes = make_pipelines()
    out = re_.calculate_risk_scores(pipes, make_obs(), weather=weather(270),
                                    reference_year=REF_YEAR)
    assert "simulated_risk_score" not in pipes.columns
    assert "Simulated Risk Score" in out.attrs["disclaimer"]


def test_missing_columns_raise_clear_error():
    bad_obs = make_obs().drop(columns=["is_ml_anomaly"])
    result = re_.calculate_risk_scores(make_pipelines(), bad_obs, weather=weather(270))
    assert result.iloc[0]["score_methane"] is None
    assert result.iloc[0]["risk_level"] == "Incomplete"


def test_scoring_survives_dead_weather_api_end_to_end():
    """weather=None -> engine fetches itself -> API dead -> still scores."""
    with mock.patch.object(re_.urllib.request, "urlopen",
                           side_effect=OSError("network down")):
        out = re_.calculate_risk_scores(make_pipelines(), make_obs(),
                                        reference_year=REF_YEAR)
    assert out.attrs["weather"]["source"] == "fallback_mock"
    assert 0 <= out.iloc[0]["simulated_risk_score"] <= 100


# ----------------------------------------------------------------------------
# Tiny runner so the tests work without pytest installed
# ----------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAIL  {name}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests) - failed}/{len(tests)} tests passed")
    sys.exit(1 if failed else 0)
