
from contextlib import asynccontextmanager
import asyncio
import logging
import os
import time

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
import json
import pandas as pd
from fastapi.encoders import jsonable_encoder

from utils.dashboard_data import load_dashboard_data
from utils.pipeline_service import (
    overview_summary,
    pipeline_record,
    pipeline_observations,
    risk_observations,
)
from utils import integrations
from utils import sensor_state, report_builder, risk_engine
from backend import ai_analyst

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.dashboard_data = load_dashboard_data()
    ai_analyst.log_startup_configuration()
    yield


app = FastAPI(
    title="MethaTrace API",
    description="Pipeline intelligence and methane monitoring API",
    version="1.0.0",
    lifespan=lifespan,
)

_DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def _parse_cors_origins(configured: str | None) -> list[str]:
    origins = [
        origin.strip().rstrip("/")
        for origin in (configured if configured is not None else _DEFAULT_CORS_ORIGINS).split(",")
        if origin.strip()
    ]
    if "*" in origins:
        raise ValueError("CORS_ORIGINS must list explicit origins; wildcard origins are not allowed.")
    return origins


_cors_origins = _parse_cors_origins(os.getenv("CORS_ORIGINS"))

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)


def get_data():
    data = getattr(app.state, "dashboard_data", None)

    if data is None or not data.ok:
        raise HTTPException(
            status_code=503,
            detail="Pipeline dataset is unavailable.",
        )

    return data


@app.get("/")
def root():
    return {
        "name": "MethaTrace API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
    }


@app.get("/health", include_in_schema=False)
@app.get("/api/health")
def health():
    data = getattr(app.state, "dashboard_data", None)

    return {
        "status": "healthy" if data and data.ok else "degraded",
        "pipelines_available": bool(data and data.ok),
        "observations_available": bool(data and data.has_observations),
        "risk_engine_available": integrations.risk_engine_status()[0],
    }


@app.get("/api/dashboard/summary")
def dashboard_summary():
    data = get_data()

    return overview_summary(
        data.pipelines,
        data.observations,
    )


@app.get("/api/pipelines")
def get_pipelines():
    data = get_data()

    records = []

    for _, row in data.pipelines.iterrows():
        records.append(pipeline_record(data.pipelines, str(row["pipeline_id"])))

    return {
        "total": len(records),
        "pipelines": records,
    }

@app.get("/api/pipelines/geojson")
def get_pipeline_geojson():
    data = get_data()

    try:
        geojson = json.loads(data.pipelines.to_json())
        return JSONResponse(content=jsonable_encoder(geojson))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to generate pipeline GeoJSON: {exc}",
        )

@app.get("/api/pipelines/{pipeline_id}")
def get_pipeline(pipeline_id: str):
    data = get_data()

    record = pipeline_record(
        data.pipelines,
        pipeline_id,
    )

    if record is None:
        raise HTTPException(
            status_code=404,
            detail=f"Pipeline '{pipeline_id}' not found.",
        )

    observations = pipeline_observations(
        data.observations,
        pipeline_id,
    )

    return {
        "pipeline": record,
        "observation_count": len(observations),
    }


def _observation_records(observations):
    """Convert a frame to JSON-friendly records, normalizing pandas NaN/NaT."""
    if observations is None or observations.empty:
        return []
    records = observations.copy().astype(object).where(pd.notna(observations), None).to_dict("records")
    return jsonable_encoder(records)


def _get_pipeline_record(data, pipeline_id):
    record = pipeline_record(data.pipelines, pipeline_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found.")
    return record


@app.get("/api/observations")
def get_observations(
    limit: int = 100,
    offset: int = 0,
):
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000.")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must be non-negative.")

    data = get_data()
    observations = data.observations
    page = observations.iloc[offset:offset + limit]
    return {
        "total": int(len(observations)),
        "limit": limit,
        "offset": offset,
        "observations": _observation_records(page),
    }


@app.get("/api/pipelines/{pipeline_id}/observations")
def get_pipeline_observations(
    pipeline_id: str,
    limit: int = 100,
    offset: int = 0,
):
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000.")
    if offset < 0:
        raise HTTPException(status_code=422, detail="offset must be non-negative.")
    data = get_data()
    _get_pipeline_record(data, pipeline_id)
    observations = pipeline_observations(data.observations, pipeline_id)
    page = observations.iloc[offset:offset + limit]
    return {
        "pipeline_id": pipeline_id,
        "total": int(len(observations)),
        "limit": limit,
        "offset": offset,
        "observations": _observation_records(page),
    }


def _sensor_reading(data, pipeline_id):
    record = _get_pipeline_record(data, pipeline_id)
    state = getattr(app.state, "sensor_state", None)
    if state is None:
        state = {}
        app.state.sensor_state = state
    return sensor_state.get_reading(state, pipeline_id, record.get("pressure_bar"))


@app.get("/api/sensors")
def get_sensor_monitoring():
    data = get_data()
    state = getattr(app.state, "sensor_state", None)
    if state is None:
        state = {}
        app.state.sensor_state = state
    readings = sensor_state.fleet_readings(state, data.pipelines)
    return {
        **sensor_state.alert_summary(readings),
        "simulated": True,
        "readings": list(readings.values()),
    }


@app.get("/api/sensors/{pipeline_id}")
def get_pipeline_sensor(pipeline_id: str):
    reading = _sensor_reading(get_data(), pipeline_id)
    return {**reading, "simulated": True}


@app.get("/api/risk")
def get_fleet_risk():
    """Assess the pipeline fleet in one engine pass and one weather lookup."""
    data = get_data()
    try:
        weather = risk_engine.fetch_current_weather()
        assessed = risk_engine.calculate_risk_scores(
            data.pipelines,
            data.observations,
            weather=weather,
        )
        state = getattr(app.state, "sensor_state", None)
        if state is None:
            state = {}
            app.state.sensor_state = state
        readings = sensor_state.fleet_readings(state, data.pipelines)
        assessments = []
        for _, row in assessed.iterrows():
            pipeline_id = str(row["pipeline_id"])
            reading = readings.get(pipeline_id, {})
            score = row["simulated_risk_score"]
            assessments.append({
                "pipeline_id": pipeline_id,
                "score": None if pd.isna(score) else float(score),
                "level": str(row["risk_level"]),
                "data_quality": str(row["data_quality"]),
                "scored_maximum": float(row["scored_maximum"]),
                "sensor_alert": bool(reading.get("is_anomaly", False)),
            })
        return {
            "assessments": assessments,
            "weather": weather,
            "simulated": True,
        }
    except Exception as exc:
        logger.error("Fleet risk assessment failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="Unable to assess pipeline fleet risk.") from None


@app.get("/api/risk/{pipeline_id}")
def get_pipeline_risk(pipeline_id: str):
    data = get_data()

    record = _get_pipeline_record(data, pipeline_id)
    pipeline_match = data.pipelines[data.pipelines["pipeline_id"] == pipeline_id]
    if pipeline_match.empty:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' was not found.")
    # Match the fleet endpoint's canonical inputs: source geometry, complete
    # observation set, and a single weather snapshot for this assessment.
    record["geometry"] = pipeline_match.iloc[0]["geometry"]

    observations = risk_observations(
        data.pipelines,
        data.observations,
        pipeline_id,
    )

    sensor_reading = _sensor_reading(data, pipeline_id)
    weather = risk_engine.fetch_current_weather()
    result = integrations.assess_risk(
        record,
        data.observations,
        sensor_reading=sensor_reading,
        weather=weather,
    )

    if result.status == integrations.STATUS_ERROR:
        logger.warning("Pipeline risk assessment failed for %s: %s", pipeline_id, result.message.split(":", 1)[0])
        raise HTTPException(status_code=502, detail="The pipeline risk assessment is temporarily unavailable.") from None

    def anomaly_count(column):
        if observations is None or observations.empty or column not in observations.columns:
            return 0
        return int(observations[column].fillna(False).astype(bool).sum())

    signals = {
        "operational_status": record.get("status"),
        "sensor_status": sensor_reading.get("sensor_status"),
        "sensor_alert": bool(sensor_reading.get("is_anomaly", False)),
        "threshold_anomalies": anomaly_count("is_threshold_anomaly"),
        "ml_anomalies": anomaly_count("is_ml_anomaly"),
        "observation_count": int(len(observations)) if observations is not None else 0,
    }
    return {
        "pipeline_id": pipeline_id,
        "status": result.status,
        "score": result.score,
        "level": result.level,
        "factors": list(result.factors),
        "factor_breakdown": list(result.factor_breakdown),
        "scored_maximum": result.scored_maximum,
        "data_quality": result.data_quality,
        "missing_factors": list(result.missing_factors),
        "signals": signals,
        "weather": result.weather,
        "simulated": True,
        "message": result.message,
        "disclaimer": "Simulated prototype indicator; not a calibrated failure probability or safety assessment.",
    }


@app.post("/api/ai/chat")
async def ai_chat(request: ai_analyst.AIChatRequest):
    request_started = time.perf_counter()
    logger.info("AI endpoint request received")
    data = get_data()
    state = getattr(app.state, "sensor_state", None)
    if state is None:
        state = {}
        app.state.sensor_state = state
    try:
        async with asyncio.timeout(ai_analyst.BACKEND_TIMEOUT_SECONDS):
            result = await ai_analyst.chat(request, data, state)
        serialization_started = time.perf_counter()
        response = JSONResponse(content=jsonable_encoder(result))
        logger.info(
            "AI endpoint response serialization completed: duration_ms=%.1f",
            (time.perf_counter() - serialization_started) * 1000,
        )
        logger.info("AI endpoint completed: duration_ms=%.1f", (time.perf_counter() - request_started) * 1000)
        return response
    except asyncio.CancelledError:
        logger.info("AI endpoint request cancelled: duration_ms=%.1f", (time.perf_counter() - request_started) * 1000)
        raise
    except asyncio.TimeoutError:
        logger.warning("AI endpoint timed out: category=backend_deadline duration_ms=%.1f", (time.perf_counter() - request_started) * 1000)
        raise HTTPException(status_code=504, detail="AI Analyst exceeded the 70-second backend request limit. Please retry.") from None
    except HTTPException as exc:
        logger.info("AI endpoint returned error: status=%s duration_ms=%.1f", exc.status_code, (time.perf_counter() - request_started) * 1000)
        raise


@app.get("/api/reports/{pipeline_id}.pdf")
def get_pipeline_report(pipeline_id: str):
    data = get_data()
    record = _get_pipeline_record(data, pipeline_id)
    pipeline_match = data.pipelines[data.pipelines["pipeline_id"] == pipeline_id]
    if pipeline_match.empty:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' was not found.")
    record["geometry"] = pipeline_match.iloc[0]["geometry"]
    reading = _sensor_reading(data, pipeline_id)
    weather = risk_engine.fetch_current_weather()
    risk = integrations.assess_risk(
        record,
        data.observations,
        sensor_reading=reading,
        weather=weather,
    )
    try:
        report_id, pdf_bytes = report_builder.build_pdf(pipeline_id, data, reading, risk)
    except ImportError:
        logger.error("PDF report generation dependency unavailable: %s", pipeline_id)
        raise HTTPException(status_code=503, detail="PDF report generation is unavailable.") from None
    except Exception as exc:
        logger.error("PDF report generation failed for %s: %s", pipeline_id, type(exc).__name__)
        raise HTTPException(status_code=500, detail="Unable to generate the PDF report.") from None
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{report_id}.pdf"'},
    )
