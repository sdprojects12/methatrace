"""
Builds PDF inspection reports from live dashboard state (no Streamlit imports).
Maps the app's data model onto the generate_report() contract in utils/pdf_report.py.
"""
from __future__ import annotations

import datetime
import zlib

import pandas as pd

from utils.pipeline_service import (
    METHANE_THRESHOLD_PPM,
    anomaly_info,
    pipeline_observations,
    pipeline_record,
)

MAX_REPORT_OBSERVATIONS = 25
DEMO_NOTE = "Demonstration output generated from synthetic data; not for operational decisions."


def make_report_id(pipeline_id: str, reading: dict, now: datetime.datetime = None) -> str:
    """Stable for identical state on the same day, so reruns do not change the file name."""
    now = now or datetime.datetime.now()
    basis = f"{pipeline_id}|{reading.get('pressure_bar')}|{reading.get('flow_rate_m3h')}|{reading.get('scenario')}"
    return f"MT-{pipeline_id}-{now:%Y%m%d}-{zlib.crc32(basis.encode()) :08X}"


def recommendations_for(record: dict, reading: dict, obs: pd.DataFrame, risk=None) -> list:
    """Rule-based statements derived only from the current state of the selected pipeline."""
    recs = []
    info = anomaly_info(obs)

    if reading and reading.get("is_anomaly"):
        base = reading.get("baseline_pressure_bar") or 0
        drop = abs(reading.get("pressure_delta_bar", 0))
        pct = f" ({drop / base * 100:.0f}%)" if base else ""
        recs.append(
            f"Simulated sensor anomaly: pressure {drop:.2f} bar below the simulated baseline{pct} and flow "
            f"{reading.get('flow_delta_m3h', 0):+.2f} m3/h. Verify telemetry and sensor integrity."
        )
    if info["threshold_anomaly_count"]:
        recs.append(
            f"{info['threshold_anomaly_count']} methane observation(s) above {METHANE_THRESHOLD_PPM:g} ppm are "
            f"located near this segment (maximum {obs['methane_concentration_ppm'].max():.2f} ppm). "
            "Review the observations listed in this report."
        )
    if info["ml_anomaly_count"]:
        recs.append(
            f"{info['ml_anomaly_count']} observation(s) near this segment were flagged as statistical outliers "
            "by the Isolation Forest model; these are not confirmed leaks."
        )
    if record and record.get("status") not in (None, "Active"):
        recs.append(f"Operational status is '{record['status']}'. Confirm this against maintenance records.")
    if risk is not None and getattr(risk, "available", False):
        parts = [p for p in (risk.level, None if risk.score is None else f"score {risk.score:g}") if p]
        recs.append(f"Risk engine assessment: {', '.join(parts)}.")

    if not recs:
        recs.append("No anomalies were found for this segment in the current synthetic data. Continue routine monitoring.")
    recs.append(DEMO_NOTE)
    return recs


def build_report_inputs(pipeline_id: str, data, reading: dict, risk=None,
                        max_observations: int = MAX_REPORT_OBSERVATIONS) -> dict:
    """Arguments for generate_report() (except report_id) for the selected pipeline."""
    record = pipeline_record(data.pipelines, pipeline_id)
    if record is None:
        raise ValueError(f"Unknown pipeline: {pipeline_id!r}")

    obs = pipeline_observations(data.observations, pipeline_id)
    flagged = obs["is_threshold_anomaly"] | obs["is_ml_anomaly"] if not obs.empty else pd.Series(dtype=bool)
    table = pd.DataFrame()
    if not obs.empty:
        table = obs.assign(_flagged=flagged).sort_values(["_flagged", "timestamp"], ascending=False).head(max_observations).copy()
        # The PDF's "Threshold Anomaly" column reads is_anomaly; feed it the recomputed threshold flag.
        table["is_anomaly"] = table["is_threshold_anomaly"]

    sensor = {
        "pressure_bar": reading["pressure_bar"],
        "flow_rate_m3h": reading["flow_rate_m3h"],
        "sensor_status": f"{reading['sensor_status']} [scenario: {reading.get('scenario', 'n/a')}]",
    }
    return {
        "pipeline": record,
        "sensor_readings": sensor,
        "observations_df": table,
        "anomaly_info": anomaly_info(obs),
        "recommendations": recommendations_for(record, reading, obs, risk),
    }


def build_pdf(pipeline_id: str, data, reading: dict, risk=None, now: datetime.datetime = None) -> tuple:
    """Returns (report_id, pdf_bytes). Raises on failure so the UI can report it."""
    from utils.pdf_report import generate_report  # deferred: ReportLab is only needed here

    report_id = make_report_id(pipeline_id, reading, now)
    pdf = generate_report(report_id=report_id, **build_report_inputs(pipeline_id, data, reading, risk))
    return report_id, pdf
