"""
Integration points for modules developed outside the dashboard.

Nothing here implements a risk model or a weather client. This file only *discovers* the
modules if they exist and adapts them to a stable shape, so the dashboard never breaks when
they are absent, slow, or raise.

PROPOSED CONTRACTS (agree with the module owner; change the constants below if they differ)

  utils/risk_engine.py
      assess_pipeline_risk(pipeline: dict, observations: pandas.DataFrame,
                           sensor_reading: dict | None, weather: dict | None) -> dict | object
      Return value needs: score (number, optional), level (str, optional), factors (list[str], optional).

  utils/weather_api.py
      get_conditions(latitude: float, longitude: float) -> dict | None

Both are called with keyword arguments. Any exception, signature mismatch or malformed result
is converted into a status of "error" with a message; the dashboard shows that instead of crashing.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field

RISK_MODULE = "utils.risk_engine"
RISK_ENTRY_POINT = "assess_pipeline_risk"
WEATHER_MODULE = "utils.weather_api"
WEATHER_ENTRY_POINT = "get_conditions"

STATUS_OK = "ok"
STATUS_UNAVAILABLE = "unavailable"
STATUS_ERROR = "error"


@dataclass(frozen=True)
class RiskResult:
    status: str
    pipeline_id: str = None
    score: float = None
    level: str = None
    factors: tuple = ()
    message: str = ""
    factor_breakdown: tuple = ()
    weather: dict = field(default_factory=dict)
    scored_maximum: float = None
    data_quality: str = ""
    missing_factors: tuple = ()

    @property
    def available(self) -> bool:
        return self.status == STATUS_OK


@dataclass(frozen=True)
class WeatherResult:
    status: str
    data: dict = field(default_factory=dict)
    message: str = ""

    @property
    def available(self) -> bool:
        return self.status == STATUS_OK


def _resolve(module_name: str, entry_point: str):
    """Returns (callable | None, reason). Distinguishes 'module absent' from 'module broken'."""
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        if e.name == module_name:
            return None, f"{module_name} is not present yet."
        return None, f"{module_name} failed to import: missing dependency '{e.name}'."
    except Exception as e:
        return None, f"{module_name} failed to import: {e}"
    func = getattr(module, entry_point, None)
    if not callable(func):
        return None, f"{module_name} does not define {entry_point}()."
    return func, ""


def risk_engine_status() -> tuple:
    func, reason = _resolve(RISK_MODULE, RISK_ENTRY_POINT)
    return func is not None, reason


def weather_status() -> tuple:
    func, reason = _resolve(WEATHER_MODULE, WEATHER_ENTRY_POINT)
    return func is not None, reason


def _field(raw, name):
    return raw.get(name) if isinstance(raw, dict) else getattr(raw, name, None)


def assess_risk(pipeline: dict, observations, sensor_reading: dict = None, weather: dict = None) -> RiskResult:
    pid = (pipeline or {}).get("pipeline_id")
    func, reason = _resolve(RISK_MODULE, RISK_ENTRY_POINT)
    if func is None:
        return RiskResult(STATUS_UNAVAILABLE, pid, message=reason)
    try:
        raw = func(pipeline=pipeline, observations=observations, sensor_reading=sensor_reading, weather=weather)
    except Exception as e:
        return RiskResult(STATUS_ERROR, pid, message=f"Risk engine call failed: {type(e).__name__}: {e}")
    if raw is None:
        return RiskResult(STATUS_ERROR, pid, message="Risk engine returned no result.")

    score = _field(raw, "score")
    level = _field(raw, "level")
    factors = _field(raw, "factors")
    factor_breakdown = _field(raw, "factor_breakdown")
    weather = _field(raw, "weather")
    scored_maximum = _field(raw, "scored_maximum")
    data_quality = _field(raw, "data_quality")
    missing_factors = _field(raw, "missing_factors")
    if score is None and level is None:
        return RiskResult(STATUS_ERROR, pid, message="Risk engine result has neither 'score' nor 'level'.")
    try:
        score = None if score is None else float(score)
    except (TypeError, ValueError):
        return RiskResult(STATUS_ERROR, pid, message="Risk engine returned a non-numeric score.")
    try:
        scored_maximum = None if scored_maximum is None else float(scored_maximum)
    except (TypeError, ValueError):
        return RiskResult(STATUS_ERROR, pid, message="Risk engine returned a non-numeric scored maximum.")
    return RiskResult(
        STATUS_OK, pid, score=score,
        level=None if level is None else str(level),
        factors=tuple(str(f) for f in (factors or ())),
        factor_breakdown=tuple(factor_breakdown or ()),
        weather=dict(weather or {}),
        scored_maximum=scored_maximum,
        data_quality="" if data_quality is None else str(data_quality),
        missing_factors=tuple(str(factor) for factor in (missing_factors or ())),
    )


def get_weather(latitude: float, longitude: float) -> WeatherResult:
    func, reason = _resolve(WEATHER_MODULE, WEATHER_ENTRY_POINT)
    if func is None:
        return WeatherResult(STATUS_UNAVAILABLE, message=reason)
    try:
        raw = func(latitude=latitude, longitude=longitude)
    except Exception as e:
        return WeatherResult(STATUS_ERROR, message=f"Weather request failed: {type(e).__name__}: {e}")
    if not isinstance(raw, dict) or not raw:
        return WeatherResult(STATUS_ERROR, message="Weather provider returned no usable data.")
    return WeatherResult(STATUS_OK, data=raw)
