
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from utils.dashboard_data import load_dashboard_data
from utils.pipeline_service import (
    overview_summary,
    pipeline_record,
    pipeline_observations,
)
from utils import integrations


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.dashboard_data = load_dashboard_data()
    yield


app = FastAPI(
    title="MethaTrace API",
    description="Pipeline intelligence and methane monitoring API",
    version="1.0.0",
    lifespan=lifespan,
)

# Development frontend origins.
# We'll replace these with the deployed frontend URL later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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


@app.get("/api/health")
def health():
    data = getattr(app.state, "dashboard_data", None)

    return {
        "status": "healthy" if data and data.ok else "degraded",
        "pipelines_available": bool(data and data.ok),
        "observations_available": bool(data and data.has_observations),
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
        record = pipeline_record(
            data.pipelines,
            str(row["pipeline_id"]),
        )

        records.append(record)

    return {
        "total": len(records),
        "pipelines": records,
    }


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


@app.get("/api/risk/{pipeline_id}")
def get_pipeline_risk(pipeline_id: str):
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

    result = integrations.assess_risk(
        record,
        observations,
    )

    return {
        "pipeline_id": pipeline_id,
        "status": result.status,
        "score": result.score,
        "level": result.level,
        "factors": list(result.factors),
        "simulated": True,
        "message": result.message,
    }
