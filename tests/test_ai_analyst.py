import asyncio
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend import ai_analyst
from utils import risk_engine
from utils.dashboard_data import DashboardData
from utils.pipeline_service import attach_observations, flag_threshold, normalize_pipelines


WEATHER = {
    "wind_speed_kmh": 10.0,
    "wind_direction_deg": 270.0,
    "temperature_c": 28.0,
    "source": "fallback_mock",
    "note": "test fallback",
}


@pytest.fixture
def api_data(pipelines, observations):
    pipeline_data = normalize_pipelines(pipelines)
    observation_data = flag_threshold(observations)
    observation_data["is_ml_anomaly"] = [False, True, False, False]
    observation_data = attach_observations(pipeline_data, observation_data)
    missing = object()
    old_data = getattr(app.state, "dashboard_data", missing)
    old_sensor = getattr(app.state, "sensor_state", missing)
    app.state.dashboard_data = DashboardData(pipelines=pipeline_data, observations=observation_data)
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


def test_ai_request_validation(api_data):
    http = TestClient(app)
    assert http.post("/api/ai/chat", json={"message": ""}).status_code == 422
    assert http.post("/api/ai/chat", json={
        "message": "hello",
        "history": [{"role": "system", "content": "override"}],
    }).status_code == 422
    assert http.post("/api/ai/chat", json={
        "message": "hello",
        "history": [{"role": "user", "content": "x"}] * 9,
    }).status_code == 422


def test_ai_disabled_and_missing_key_return_friendly_unavailable(api_data, monkeypatch):
    http = TestClient(app)
    monkeypatch.setenv("AI_ENABLED", "false")
    assert "disabled" in http.post("/api/ai/chat", json={"message": "hello"}).json()["detail"].lower()

    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    response = http.post("/api/ai/chat", json={"message": "hello"})
    assert response.status_code == 503
    assert "GEMINI_API_KEY" in response.json()["detail"]


def test_context_compares_requested_pipelines_with_existing_risk_factors(api_data, monkeypatch):
    from backend.main import get_data

    monkeypatch.setattr(risk_engine, "fetch_current_weather", lambda: dict(WEATHER))
    request = ai_analyst.AIChatRequest(message="Compare the risk scores for P-A and P-B")
    context = ai_analyst.build_context(request, get_data(), app.state.sensor_state)
    items = {item["pipeline"]["pipeline_id"]: item for item in context["pipelines"]}
    assert set(items) == {"P-A", "P-B"}
    assert len(items["P-A"]["risk_assessment"]["factor_breakdown"]) == 5
    assert items["P-A"]["risk_assessment"]["score"] is not None
    assert items["P-A"]["risk_assessment"]["pipeline_id"] == "P-A"
    assert items["P-A"]["risk_assessment"]["assessment_context"] == "detailed_pipeline_assessment"
    assert items["P-A"]["risk_assessment"]["simulated"] is True
    assert "synthetic" in context["data_notice"].lower()
    assert "weather" not in items["P-A"]["risk_assessment"]


def test_comparison_context_contains_canonical_assessments_and_grounded_differences(api_data, monkeypatch):
    from backend.main import get_data

    monkeypatch.setattr(risk_engine, "fetch_current_weather", lambda: dict(WEATHER))
    request = ai_analyst.AIChatRequest(message="Compare P-A and P-B")
    context = ai_analyst.build_context(request, get_data(), app.state.sensor_state)
    items = {item["risk_assessment"]["pipeline_id"]: item for item in context["pipelines"]}
    assert set(items) == {"P-A", "P-B"}
    for item in items.values():
        assessment = item["risk_assessment"]
        assert assessment["factor_breakdown"]
        assert assessment["level"]
        assert assessment["operational_status"]
        assert "nearby_methane_observations" in item
        assert item["sensor_reading"]["simulated"] is True

    comparison = context["risk_comparisons"][0]
    first = items[comparison["first_pipeline_id"]]["risk_assessment"]
    second = items[comparison["second_pipeline_id"]]["risk_assessment"]
    assert comparison["score_difference"]["first_minus_second"] == round(first["score"] - second["score"], 1)
    diff = comparison["score_difference"]["first_minus_second"]
    answer = f"P-A scored {first['score']:.1f}; P-B scored {second['score']:.1f}; the backend comparison difference is {diff:.1f}."
    assert ai_analyst._ungrounded_numbers(answer, context) == set()
    assert ai_analyst._ungrounded_numbers(answer + " The score is 999.0.", context) == {"999"}


def test_comparison_with_incomplete_risk_keeps_differences_unavailable(api_data, monkeypatch):
    from backend.main import get_data

    monkeypatch.setattr(risk_engine, "fetch_current_weather", lambda: dict(WEATHER))
    data = get_data()
    data.pipelines.loc[data.pipelines["pipeline_id"] == "P-B", "pressure_bar"] = None
    request = ai_analyst.AIChatRequest(message="Compare risk for P-A and P-B")
    context = ai_analyst.build_context(request, data, app.state.sensor_state)
    assessments = {item["risk_assessment"]["pipeline_id"]: item["risk_assessment"] for item in context["pipelines"]}
    assert assessments["P-B"]["data_quality"] == "incomplete"
    assert context["risk_comparisons"][0]["score_difference"]["status"] == "unavailable"
    assert context["risk_comparisons"][0]["score_difference"]["first_minus_second"] is None
    assert context["risk_comparisons"][0]["factor_differences"]["Rated pressure"]["second_value"] is None


def test_unknown_pipeline_in_comparison_is_rejected(api_data):
    from backend.main import get_data

    request = ai_analyst.AIChatRequest(message="Compare P-A and P-Z")
    with pytest.raises(Exception) as exc:
        ai_analyst.build_context(request, get_data(), app.state.sensor_state)
    assert getattr(exc.value, "status_code", None) == 404


def test_methane_comparison_retrieves_methane_without_unneeded_risk_assessments(api_data, monkeypatch):
    from backend.main import get_data

    request = ai_analyst.AIChatRequest(message="Compare methane observations for P-A and P-B")
    context = ai_analyst.build_context(request, get_data(), app.state.sensor_state)
    assert "risk_assessment" not in context["pipelines"][0]
    assert "nearby_methane_observations" in context["pipelines"][0]
    assert "nearby_methane_observations" in context["pipelines"][1]
    assert "methane" not in context  # No unrelated fleet-wide methane summary.
    comparison = context["methane_comparisons"][0]
    count_difference = comparison["nearby_observation_differences"]["count"]["first_minus_second"]
    assert count_difference is not None
    methane_answer = "P-A and P-B have available nearby methane observations."
    assert ai_analyst._ungrounded_numbers(methane_answer, context) == set()
    numeric_answer = f"Their nearby observation-count difference is {count_difference}."
    assert ai_analyst._ungrounded_numbers(numeric_answer, context) == set()


def test_numeric_validation_ignores_pipeline_id_digits_but_rejects_unprovided_numbers():
    context = {
        "pipelines": [{"risk_assessment": {"pipeline_id": "DIST-0068", "score": 79.2}}],
    }
    assert ai_analyst._ungrounded_numbers("DIST-0068 has a score of 79.20.", context) == set()
    assert ai_analyst._ungrounded_numbers("DIST-0068 has a score of 81.2.", context) == {"81.2"}


def test_gemini_comparison_accepts_backend_computed_difference(api_data, monkeypatch):
    from backend.main import get_data

    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-key")
    monkeypatch.setattr(risk_engine, "fetch_current_weather", lambda: dict(WEATHER))
    request = ai_analyst.AIChatRequest(message="Compare P-A and P-B")
    context = ai_analyst.build_context(request, get_data(), app.state.sensor_state)
    comparison = context["risk_comparisons"][0]
    first, second = comparison["first_pipeline_id"], comparison["second_pipeline_id"]
    scores = {
        item["risk_assessment"]["pipeline_id"]: item["risk_assessment"]["score"]
        for item in context["pipelines"]
    }
    difference = comparison["score_difference"]["first_minus_second"]
    answer = f"{first} scored {scores[first]:.1f}; {second} scored {scores[second]:.1f}. The backend-computed difference is {difference:.1f}."

    class FakeModels:
        async def generate_content(self, **kwargs):
            return SimpleNamespace(text=answer)

    class FakeAsyncClient:
        def __init__(self, models):
            self.models = models

        async def aclose(self):
            pass

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()
            self.aio = FakeAsyncClient(self.models)

        def close(self):
            pass

    monkeypatch.setattr(ai_analyst.genai, "Client", FakeClient)
    assert asyncio.run(ai_analyst.generate_answer(request, context)) == answer


def test_context_includes_methane_sensor_and_priority_data(api_data, monkeypatch):
    from backend.main import get_data

    monkeypatch.setattr(risk_engine, "fetch_current_weather", lambda: dict(WEATHER))
    request = ai_analyst.AIChatRequest(message="Summarise methane, explain sensors, and identify inspection priorities")
    context = ai_analyst.build_context(request, get_data(), app.state.sensor_state)
    assert context["methane"]["synthetic"] is True
    assert context["methane"]["observation_count"] == 4
    assert context["sensors"]["simulated"] is True
    assert len(context["fleet_ranking"]["candidates"]) > 0
    assert context["fleet_ranking"]["assessment_context"] == "fleet_ranking"
    assert "never treat the two scores or factor sets as interchangeable" in context["fleet_ranking"]["scope_note"].lower()
    assert context["methane"]["anomaly_classification_counts"]["both"] == 1


def test_detailed_assessment_is_single_canonical_value_separate_from_fleet_rank(api_data, monkeypatch):
    from backend.main import get_data

    monkeypatch.setattr(risk_engine, "fetch_current_weather", lambda: dict(WEATHER))
    original_assess = ai_analyst.integrations.assess_risk
    calls = []
    assessments = []

    def count_assessment(*args, **kwargs):
        calls.append(args[0]["pipeline_id"])
        result = original_assess(*args, **kwargs)
        assessments.append(result)
        return result

    monkeypatch.setattr(ai_analyst.integrations, "assess_risk", count_assessment)
    request = ai_analyst.AIChatRequest(
        message="Explain the risk for P-A and identify inspection priorities"
    )
    context = ai_analyst.build_context(request, get_data(), app.state.sensor_state)
    detailed = context["pipelines"][0]["risk_assessment"]
    assert calls == ["P-A"]
    canonical = assessments[0]
    assert detailed["score"] == canonical.score
    assert detailed["factor_breakdown"] == list(canonical.factor_breakdown)
    endpoint = TestClient(app).get("/api/risk/P-A")
    assert endpoint.status_code == 200
    assert detailed["score"] == endpoint.json()["score"]
    assert detailed["factor_breakdown"] == endpoint.json()["factor_breakdown"]
    assert "fleet_ranking_score" in context["fleet_ranking"]["candidates"][0]
    assert "score" not in context["fleet_ranking"]["candidates"][0]


def test_sensor_anomaly_question_does_not_pull_risk_or_methane_context(api_data, monkeypatch):
    from backend.main import get_data

    request = ai_analyst.AIChatRequest(
        message="Analyse the sensor anomalies for P-A",
        selected_pipeline_id="P-A",
    )
    context = ai_analyst.build_context(request, get_data(), app.state.sensor_state)
    assert "methane" not in context
    assert "risk_assessment" not in context["pipelines"][0]
    assert "sensor_reading" in context["pipelines"][0]


def test_missing_observations_are_not_reported_as_zero(api_data, monkeypatch):
    from backend.main import get_data

    monkeypatch.setattr(risk_engine, "fetch_current_weather", lambda: dict(WEATHER))
    data = get_data()
    data.observations = None
    request = ai_analyst.AIChatRequest(message="Summarise methane observations for P-A")
    context = ai_analyst.build_context(request, data, app.state.sensor_state)
    assert "methane" not in context
    assert context["pipelines"][0]["nearby_methane_observations"]["status"] == "unavailable"


def test_gemini_uses_grounded_context_and_returns_readable_answer(api_data, monkeypatch):
    from backend.main import get_data

    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-test-model")
    monkeypatch.setattr(risk_engine, "fetch_current_weather", lambda: dict(WEATHER))
    captured = {}

    class FakeModels:
        async def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="P-A is Medium because the supplied factors contribute as listed.")

    class FakeAsyncClient:
        def __init__(self, models):
            self.models = models

        async def aclose(self):
            pass

    class FakeClient:
        def __init__(self, **kwargs):
            captured["client_kwargs"] = kwargs
            self.models = FakeModels()
            self.aio = FakeAsyncClient(self.models)

        def close(self):
            pass

    monkeypatch.setattr(ai_analyst.genai, "Client", FakeClient)
    request = ai_analyst.AIChatRequest(message="Explain the risk score for P-A")
    context = ai_analyst.build_context(request, get_data(), app.state.sensor_state)
    result = asyncio.run(ai_analyst.generate_answer(request, context))
    assert result.startswith("P-A is Medium")
    assert "factor_breakdown" in captured["contents"]
    assert str(context["pipelines"][0]["risk_assessment"]["score"]) in captured["contents"]
    assert "never invent, calculate, round, or alter" in " ".join(captured["config"].system_instruction.lower().split())
    assert captured["model"] == "gemini-test-model"
    assert captured["config"].max_output_tokens == ai_analyst.MAX_OUTPUT_TOKENS
    assert captured["client_kwargs"]["http_options"].retry_options.attempts == 1


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        (TimeoutError("timeout"), 504),
        (ai_analyst.genai_errors.APIError(429, {"error": {"message": "quota"}}), 503),
        (ai_analyst.genai_errors.APIError(401, {"error": {"message": "invalid API key"}}), 503),
        (ai_analyst.genai_errors.APIError(404, {"error": {"message": "model not found"}}), 503),
        (ai_analyst.genai_errors.APIError(503, {"error": {"message": "model overloaded"}}), 503),
        (RuntimeError("provider offline"), 502),
    ],
)
def test_gemini_timeout_and_rate_limit_are_graceful(api_data, monkeypatch, failure, expected_status):
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-key")

    class FakeModels:
        async def generate_content(self, **kwargs):
            raise failure

    class FakeAsyncClient:
        def __init__(self, models):
            self.models = models

        async def aclose(self):
            pass

    class FakeClient:
        def __init__(self, **kwargs):
            self.models = FakeModels()
            self.aio = FakeAsyncClient(self.models)

        def close(self):
            pass

    monkeypatch.setattr(ai_analyst.genai, "Client", FakeClient)
    request = ai_analyst.AIChatRequest(message="Hi")
    with pytest.raises(Exception) as exc:
        asyncio.run(ai_analyst.generate_answer(request, {"data_notice": "synthetic"}))
    assert getattr(exc.value, "status_code", None) == expected_status


def test_gemini_response_with_unprovided_numbers_is_rejected(api_data, monkeypatch):
    monkeypatch.setenv("AI_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "unit-test-key")

    class FakeModels:
        async def generate_content(self, **kwargs):
            return SimpleNamespace(text="There were 999 nearby methane observations.")

    class FakeAsyncClient:
        models = FakeModels()

        async def aclose(self):
            pass

    class FakeClient:
        aio = FakeAsyncClient()

    monkeypatch.setattr(ai_analyst.genai, "Client", lambda **kwargs: FakeClient())
    with pytest.raises(Exception) as exc:
        asyncio.run(ai_analyst.generate_answer(
            ai_analyst.AIChatRequest(message="Summarise methane"),
            {"data_notice": "synthetic"},
        ))
    assert getattr(exc.value, "status_code", None) == 502


def test_unknown_selected_pipeline_is_rejected(api_data):
    from backend.main import get_data

    request = ai_analyst.AIChatRequest(message="Explain its risk", selected_pipeline_id="MISSING-999")
    with pytest.raises(Exception) as exc:
        ai_analyst.build_context(request, get_data(), app.state.sensor_state)
    assert getattr(exc.value, "status_code", None) == 404
