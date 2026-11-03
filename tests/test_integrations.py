import sys
import types

import pytest
from utils import integrations as ig


@pytest.fixture
def fake_module(monkeypatch):
    def install(name, **attrs):
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        monkeypatch.setitem(sys.modules, name, mod)
        parent, _, child = name.rpartition(".")
        monkeypatch.setattr(sys.modules[parent], child, mod, raising=False)
    return install


def test_absent_modules_are_unavailable_not_errors(monkeypatch):
    monkeypatch.setattr(ig, "RISK_MODULE", "utils.definitely_absent_risk")
    monkeypatch.setattr(ig, "WEATHER_MODULE", "utils.definitely_absent_weather")
    r = ig.assess_risk({"pipeline_id": "P"}, None)
    assert r.status == ig.STATUS_UNAVAILABLE and not r.available
    assert ig.get_weather(1.0, 2.0).status == ig.STATUS_UNAVAILABLE
    assert ig.risk_engine_status()[0] is False


def test_risk_result_adapts_dict_and_object(fake_module, monkeypatch):
    monkeypatch.setattr(ig, "RISK_MODULE", "utils.fake_risk")
    fake_module("utils.fake_risk", assess_pipeline_risk=lambda **kw: {"score": "0.7", "level": "High", "factors": ["a", "b"]})
    r = ig.assess_risk({"pipeline_id": "P"}, None, {"x": 1})
    assert r.available and r.score == 0.7 and r.level == "High" and r.factors == ("a", "b") and r.pipeline_id == "P"

    obj = types.SimpleNamespace(score=2, level=None, factors=None)
    fake_module("utils.fake_risk", assess_pipeline_risk=lambda **kw: obj)
    assert ig.assess_risk({"pipeline_id": "P"}, None).score == 2.0


def test_risk_failures_are_contained(fake_module, monkeypatch):
    monkeypatch.setattr(ig, "RISK_MODULE", "utils.fake_risk")

    def boom(**kw):
        raise RuntimeError("model crashed")
    fake_module("utils.fake_risk", assess_pipeline_risk=boom)
    r = ig.assess_risk({"pipeline_id": "P"}, None)
    assert r.status == ig.STATUS_ERROR and "model crashed" in r.message

    fake_module("utils.fake_risk", assess_pipeline_risk=lambda pipeline: {"score": 1})  # wrong signature
    assert ig.assess_risk({"pipeline_id": "P"}, None).status == ig.STATUS_ERROR

    fake_module("utils.fake_risk", assess_pipeline_risk=lambda **kw: {"unrelated": 1})
    assert ig.assess_risk({"pipeline_id": "P"}, None).status == ig.STATUS_ERROR

    fake_module("utils.fake_risk")  # entry point missing
    assert ig.assess_risk({"pipeline_id": "P"}, None).status == ig.STATUS_UNAVAILABLE


def test_weather_success_and_api_failure(fake_module, monkeypatch):
    monkeypatch.setattr(ig, "WEATHER_MODULE", "utils.fake_weather")
    fake_module("utils.fake_weather", get_conditions=lambda latitude, longitude: {"wind_kmh": 12})
    assert ig.get_weather(18.7, 73.8).data == {"wind_kmh": 12}

    def timeout(latitude, longitude):
        raise TimeoutError("API timed out")
    fake_module("utils.fake_weather", get_conditions=timeout)
    w = ig.get_weather(18.7, 73.8)
    assert w.status == ig.STATUS_ERROR and "timed out" in w.message

    fake_module("utils.fake_weather", get_conditions=lambda latitude, longitude: None)
    assert ig.get_weather(18.7, 73.8).status == ig.STATUS_ERROR
