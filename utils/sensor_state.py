"""
Stable sensor-simulation state for Streamlit reruns (no Streamlit imports).

`state` is any mutable mapping; the dashboard passes st.session_state. A reading for a
(pipeline, nonce) pair is generated once from a deterministic seed and then served from the
store, so unrelated reruns never change what the UI shows. The anomaly scenario is the
degraded version of the same baseline, so switching scenarios is consistent.
"""
from __future__ import annotations

import zlib

from utils.sensor_sim import generate_sensor_readings

SCENARIO_NORMAL = "Normal"
SCENARIO_ANOMALY = "Pressure-drop anomaly"
SCENARIOS = (SCENARIO_NORMAL, SCENARIO_ANOMALY)

_KEY = "sensor_sim_store"


def _store(state) -> dict:
    if _KEY not in state:
        state[_KEY] = {"scenarios": {}, "nonces": {}, "readings": {}}
    return state[_KEY]


def get_scenario(state, pipeline_id: str) -> str:
    return _store(state)["scenarios"].get(pipeline_id, SCENARIO_NORMAL)


def set_scenario(state, pipeline_id: str, scenario: str) -> None:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario!r}")
    _store(state)["scenarios"][pipeline_id] = scenario


def regenerate(state, pipeline_id: str) -> None:
    """Draws a new baseline for this pipeline on the next read."""
    store = _store(state)
    store["nonces"][pipeline_id] = store["nonces"].get(pipeline_id, 0) + 1


def reset_all(state) -> None:
    """Returns every pipeline to the Normal scenario (readings keep their baselines)."""
    _store(state)["scenarios"].clear()


def anomaly_pipeline_ids(state) -> list:
    return [p for p, s in _store(state)["scenarios"].items() if s == SCENARIO_ANOMALY]


def _seed(pipeline_id: str, nonce: int) -> int:
    return zlib.crc32(f"{pipeline_id}|{nonce}".encode("utf-8"))


def get_reading(state, pipeline_id: str, base_pressure_bar: float = None) -> dict:
    store = _store(state)
    scenario = store["scenarios"].get(pipeline_id, SCENARIO_NORMAL)
    nonce = store["nonces"].get(pipeline_id, 0)
    key = (scenario, nonce, base_pressure_bar)

    cached = store["readings"].get(pipeline_id)
    if cached is not None and cached["key"] == key:
        return cached["reading"]

    reading = generate_sensor_readings(
        pipeline_id,
        trigger_anomaly=(scenario == SCENARIO_ANOMALY),
        seed=_seed(pipeline_id, nonce),
        base_pressure_bar=base_pressure_bar,
    )
    reading["scenario"] = scenario
    store["readings"][pipeline_id] = {"key": key, "reading": reading}
    return reading


def fleet_readings(state, pipelines) -> dict:
    """Current reading for every pipeline, keyed by pipeline_id."""
    out = {}
    for pid, rated in zip(pipelines["pipeline_id"], pipelines["pressure_bar"]):
        rated = None if rated != rated else float(rated)  # NaN -> None
        out[pid] = get_reading(state, pid, rated)
    return out


def alert_summary(readings: dict) -> dict:
    alerts = sorted(p for p, r in readings.items() if r.get("is_anomaly"))
    return {"monitored": len(readings), "alerts": len(alerts), "alert_ids": alerts}
