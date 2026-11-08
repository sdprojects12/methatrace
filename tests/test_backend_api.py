import pandas as pd
import pytest
from fastapi import HTTPException

from backend.main import app
from utils.dashboard_data import DashboardData
from utils.pipeline_service import attach_observations, flag_threshold, normalize_pipelines


@pytest.fixture
def client(pipelines, observations):
    pipeline_data = normalize_pipelines(pipelines)
    observation_data = flag_threshold(observations)
    observation_data["is_ml_anomaly"] = [False, True, False, False]
    observation_data = attach_observations(pipeline_data, observation_data)
    test_data = DashboardData(pipelines=pipeline_data, observations=observation_data)
    missing = object()
    old_data = getattr(app.state, "dashboard_data", missing)
    old_sensor = getattr(app.state, "sensor_state", missing)
    app.state.dashboard_data = test_data
    app.state.sensor_state = {}
    yield
    if old_data is missing:
        del app.state.dashboard_data
    else:
        app.state.dashboard_data = old_data
    if old_sensor is missing:
        del app.state.sensor_state
    else:
        app.state.sensor_state = old_sensor


def test_existing_api_routes_and_geojson_are_serializable(client):
    from backend import main
    assert main.health()["pipelines_available"] is True
    assert main.dashboard_summary()["pipeline_total"] == 2
    assert main.get_pipelines()["total"] == 2
    assert main.get_pipeline_geojson().body
    assert main.get_pipeline_geojson().body.startswith(b'{')
    assert main.get_pipeline("P-A")["observation_count"] == 2
    with pytest.raises(HTTPException) as exc:
        main.get_pipeline("missing")
    assert exc.value.status_code == 404


def test_health_api_route_is_available(client):
    from backend import main
    health_routes = {
        route.path: route
        for route in app.routes
        if getattr(route, "path", None) in ("/api/health", "/health")
    }
    assert set(health_routes) == {"/api/health", "/health"}
    assert health_routes["/api/health"].endpoint is main.health
    assert health_routes["/health"].endpoint is main.health
    assert main.health()["status"] == "healthy"


def test_cors_uses_explicit_configured_origins_without_credentials(client):
    from backend import main

    assert main._parse_cors_origins("https://app.example.com, https://admin.example.com/") == [
        "https://app.example.com",
        "https://admin.example.com",
    ]
    with pytest.raises(ValueError):
        main._parse_cors_origins("*")
    cors = next(middleware for middleware in app.user_middleware if middleware.cls.__name__ == "CORSMiddleware")
    assert cors.kwargs["allow_credentials"] is False


def test_fleet_risk_assesses_all_pipelines_in_one_engine_call(client, monkeypatch):
    from backend import main
    from utils import risk_engine
    calls = []
    calculate = risk_engine.calculate_risk_scores

    def counted_calculation(*args, **kwargs):
        calls.append("calculation")
        return calculate(*args, **kwargs)

    monkeypatch.setattr(risk_engine, "calculate_risk_scores", counted_calculation)
    monkeypatch.setattr(risk_engine, "fetch_current_weather", lambda: calls.append("weather") or {
        "wind_speed_kmh": 10.0,
        "wind_direction_deg": 270.0,
        "temperature_c": 28.0,
        "source": "fallback_mock",
        "note": "test fallback",
    })
    result = main.get_fleet_risk()
    assert calls.count("weather") == 1
    assert calls.count("calculation") == 1
    assert len(result["assessments"]) == 2
    assert {item["pipeline_id"] for item in result["assessments"]} == {"P-A", "P-B"}


def test_pipeline_observations_are_paginated_and_validated(client):
    from backend import main
    body = main.get_pipeline_observations("P-A", limit=1, offset=0)
    assert body["total"] == 2 and len(body["observations"]) == 1
    assert body["observations"][0]["observation_id"] == "O2"  # newest first
    with pytest.raises(HTTPException) as exc:
        main.get_pipeline_observations("P-A", limit=0)
    assert exc.value.status_code == 422
    with pytest.raises(HTTPException) as exc:
        main.get_pipeline_observations("missing")
    assert exc.value.status_code == 404


def test_fleet_observations_are_retrieved_with_all_fields(client):
    from backend import main
    body = main.get_observations(limit=3, offset=0)
    assert body["total"] == 4
    assert body["limit"] == 3
    assert body["offset"] == 0
    assert len(body["observations"]) == 3
    assert {
        "observation_id",
        "latitude",
        "longitude",
        "methane_concentration_ppm",
        "wind_speed_kmh",
        "wind_direction_deg",
        "is_threshold_anomaly",
        "is_ml_anomaly",
        "pipeline_id",
        "distance_m",
    } <= set(body["observations"][0])


def test_fleet_observations_support_pagination(client):
    from backend import main
    body = main.get_observations(limit=2, offset=2)
    assert body["total"] == 4
    assert [item["observation_id"] for item in body["observations"]] == ["O3", "O4"]


def test_fleet_observations_handle_empty_dataset(client):
    from backend import main
    main.app.state.dashboard_data.observations = main.app.state.dashboard_data.observations.iloc[0:0]
    body = main.get_observations()
    assert body["total"] == 0
    assert body["observations"] == []


def test_fleet_observations_validate_pagination(client):
    from backend import main
    for params in ({"limit": 0}, {"limit": 1001}, {"offset": -1}):
        with pytest.raises(HTTPException) as exc:
            main.get_observations(**params)
        assert exc.value.status_code == 422


def test_sensor_routes_label_stable_synthetic_readings(client):
    from backend import main
    first = main.get_pipeline_sensor("P-A")
    second = main.get_pipeline_sensor("P-A")
    assert first["simulated"] is True and first["synthetic"] is True
    assert first["pressure_bar"] == second["pressure_bar"]
    fleet = main.get_sensor_monitoring()
    assert fleet["simulated"] is True and fleet["monitored"] == 2
    assert len(fleet["readings"]) == 2
    with pytest.raises(HTTPException) as exc:
        main.get_pipeline_sensor("missing")
    assert exc.value.status_code == 404


def test_risk_route_returns_prototype_disclaimer(client):
    from backend import main
    body = main.get_pipeline_risk("P-A")
    assert body["simulated"] is True
    assert "not a calibrated" in body["disclaimer"]
    assert body["score"] is None or 0 <= body["score"] <= 100


def test_risk_route_returns_structured_factors_and_independent_signals(client):
    from backend import main
    body = main.get_pipeline_risk("P-A")
    assert [factor["name"] for factor in body["factor_breakdown"]] == [
        "Operational status",
        "Methane observations",
        "Pipeline age",
        "Rated pressure",
        "Wind conditions",
    ]
    assert [factor["maximum"] for factor in body["factor_breakdown"]] == [40.0, 25.0, 15.0, 10.0, 10.0]
    assert all(factor["available"] for factor in body["factor_breakdown"])
    assert sum(factor["score"] for factor in body["factor_breakdown"]) == pytest.approx(body["score"], abs=0.2)
    assert body["scored_maximum"] == 100
    assert body["data_quality"] == "complete"
    assert body["signals"] == {
        "operational_status": "Active",
        "sensor_status": "NORMAL",
        "sensor_alert": False,
        "threshold_anomalies": 1,
        "ml_anomalies": 1,
        "observation_count": 2,
    }


def test_risk_route_keeps_operational_and_sensor_signals_independent(client):
    from backend import main
    main.app.state.dashboard_data.pipelines.loc[
        main.app.state.dashboard_data.pipelines["pipeline_id"] == "P-A", "status"
    ] = "Leaking"
    body = main.get_pipeline_risk("P-A")
    assert body["signals"]["operational_status"] == "Leaking"
    assert body["signals"]["sensor_status"] == "NORMAL"
    assert body["signals"]["sensor_alert"] is False


def test_risk_route_uses_nearby_observation_even_when_owned_by_other_pipeline(client):
    from backend import main
    observations = main.app.state.dashboard_data.observations
    observations.loc[observations["observation_id"] == "O2", "pipeline_id"] = "P-B"

    body = main.get_pipeline_risk("P-A")

    assert body["signals"]["observation_count"] == 2
    assert body["signals"]["threshold_anomalies"] == 1
    assert body["signals"]["ml_anomalies"] == 1
    assert body["factor_breakdown"][1]["score"] > 0


def test_leaking_pipeline_with_normal_methane_is_not_low_risk(client):
    from backend import main
    main.app.state.dashboard_data.pipelines.loc[
        main.app.state.dashboard_data.pipelines["pipeline_id"] == "P-A", "status"
    ] = "Leaking"
    main.app.state.dashboard_data.observations["is_threshold_anomaly"] = False
    main.app.state.dashboard_data.observations["is_ml_anomaly"] = False
    body = main.get_pipeline_risk("P-A")
    assert body["signals"]["operational_status"] == "Leaking"
    assert body["signals"]["sensor_alert"] is False
    assert body["level"] != "Low"
    assert body["factor_breakdown"][0]["score"] == 40.0


def test_risk_route_distinguishes_threshold_only_from_ml_anomalies(client):
    from backend import main
    observations = main.app.state.dashboard_data.observations
    observations["is_ml_anomaly"] = False
    body = main.get_pipeline_risk("P-A")
    assert body["signals"]["threshold_anomalies"] == 1
    assert body["signals"]["ml_anomalies"] == 0
    assert body["factor_breakdown"][0]["score"] == 0.0


def test_risk_route_exposes_weather_fallback_metadata(client, monkeypatch):
    from backend import main
    from utils import risk_engine
    monkeypatch.setattr(
        risk_engine,
        "fetch_current_weather",
        lambda: {
            "wind_speed_kmh": 10.0,
            "wind_direction_deg": 270.0,
            "temperature_c": 28.0,
            "source": "fallback_mock",
            "note": "test fallback",
        },
    )
    body = main.get_pipeline_risk("P-A")
    assert body["weather"]["source"] == "fallback_mock"
    assert body["weather"]["wind_speed_kmh"] == 10.0


def test_pdf_report_uses_canonical_detailed_risk_assessment(client, monkeypatch):
    from backend import main
    from utils import risk_engine

    weather = {
        "wind_speed_kmh": 10.0,
        "wind_direction_deg": 270.0,
        "temperature_c": 28.0,
        "source": "fallback_mock",
        "note": "test fallback",
    }
    monkeypatch.setattr(risk_engine, "fetch_current_weather", lambda: dict(weather))
    expected = main.get_pipeline_risk("P-A")
    captured = {}

    def capture_pdf(pipeline_id, data, reading, risk):
        captured.update(pipeline_id=pipeline_id, risk=risk)
        return pipeline_id, b"%PDF-test"

    monkeypatch.setattr(main.report_builder, "build_pdf", capture_pdf)
    response = main.get_pipeline_report("P-A")
    assert response.body.startswith(b"%PDF")
    assert captured["pipeline_id"] == "P-A"
    assert captured["risk"].score == expected["score"]
    assert captured["risk"].level == expected["level"]
    assert list(captured["risk"].factor_breakdown) == expected["factor_breakdown"]


def test_risk_route_handles_missing_observations_and_sensor(client, monkeypatch):
    from backend import main
    main.app.state.dashboard_data.observations = None
    monkeypatch.setattr(main, "_sensor_reading", lambda data, pipeline_id: {})
    body = main.get_pipeline_risk("P-A")
    assert body["score"] is not None
    assert body["signals"]["observation_count"] == 0
    assert body["signals"]["sensor_status"] is None
    assert body["signals"]["sensor_alert"] is False


def test_report_download_and_missing_dependency_response(client, monkeypatch):
    from backend import main
    def missing_report(*args, **kwargs):
        raise ImportError("reportlab unavailable")
    monkeypatch.setattr(main.report_builder, "build_pdf", missing_report)
    with pytest.raises(HTTPException) as exc:
        main.get_pipeline_report("P-A")
    assert exc.value.status_code == 503
    assert "PDF report generation is unavailable" in exc.value.detail
    with pytest.raises(HTTPException) as exc:
        main.get_pipeline_report("missing")
    assert exc.value.status_code == 404


def test_report_download_returns_pdf(client, monkeypatch):
    from backend import main
    monkeypatch.setattr(main.report_builder, "build_pdf", lambda *a, **k: ("MT-P-A", b"%PDF-demo"))
    response = main.get_pipeline_report("P-A")
    assert response.media_type == "application/pdf"
    assert response.headers["content-disposition"] == 'attachment; filename="MT-P-A.pdf"'
    assert response.body.startswith(b"%PDF")
