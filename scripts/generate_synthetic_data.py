"""Generate the deterministic synthetic MethaTrace observation dataset.

Pipeline geometries and operational statuses are read from the existing
``chakan_pipelines_simulated.geojson`` file and are never regenerated here.
All readings remain simulated and are not real methane measurements.
"""

import csv
import datetime as dt
import json
import math
import random
import shutil
from pathlib import Path

import geopandas as gpd
from shapely.geometry import Point


SEED = 20261107
OBSERVATION_COUNT = 600
PIPELINE_EVENT_COUNT = 48
BACKGROUND_COUNT = OBSERVATION_COUNT - (2 * PIPELINE_EVENT_COUNT)
OBSERVATION_THRESHOLD_PPM = 5.0
METRIC_CRS = "EPSG:32643"
REFERENCE_END = dt.datetime(2026, 1, 15, 12, 0, 0)

DATA_DIR = Path(__file__).resolve().parents[1] / "data"
PIPELINES_PATH = DATA_DIR / "chakan_pipelines_simulated.geojson"
OBSERVATIONS_PATH = DATA_DIR / "methane_observations.csv"
BACKUP_PATH = DATA_DIR / "methane_observations.csv.original.bak"

CHAKAN_ZONES = [
    {"lon": 73.818, "lat": 18.748},
    {"lon": 73.791, "lat": 18.790},
    {"lon": 73.800, "lat": 18.775},
    {"lon": 73.820, "lat": 18.715},
]
LEAKING_PIPELINES = ("DIST-0068", "DIST-0129")
WIND_DIRECTION_DEG = 45.0
WIND_SPEED_KMH = 15.0


def _timestamp(rng: random.Random, hours: float = 168.0) -> str:
    value = REFERENCE_END - dt.timedelta(hours=rng.uniform(0, hours))
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _background_observation(index: int, rng: random.Random) -> dict:
    zone = rng.choice(CHAKAN_ZONES)
    return {
        "observation_id": f"OBS-{index:04d}",
        "timestamp": _timestamp(rng),
        "latitude": round(zone["lat"] + rng.uniform(-0.04, 0.04), 6),
        "longitude": round(zone["lon"] + rng.uniform(-0.04, 0.04), 6),
        "methane_concentration_ppm": round(rng.uniform(1.85, 2.85), 2),
        "wind_speed_kmh": round(WIND_SPEED_KMH + rng.uniform(-3, 3), 1),
        "wind_direction_deg": round(WIND_DIRECTION_DEG + rng.uniform(-5, 5), 1),
        "source_label": "Synthetic Background",
        "is_anomaly": False,
    }


def _pipeline_event_observation(
    index: int,
    pipeline_line,
    rng: random.Random,
) -> dict:
    line_length = pipeline_line.length
    along_line = line_length * rng.uniform(0.12, 0.88)
    base = pipeline_line.interpolate(along_line)

    before = pipeline_line.interpolate(max(0.0, along_line - 1.0))
    after = pipeline_line.interpolate(min(line_length, along_line + 1.0))
    tangent = math.atan2(after.y - before.y, after.x - before.x)
    offset_angle = tangent + (math.pi / 2.0 if rng.random() < 0.5 else -math.pi / 2.0)
    offset_m = rng.uniform(18.0, 180.0)
    point = Point(
        base.x + math.cos(offset_angle) * offset_m,
        base.y + math.sin(offset_angle) * offset_m,
    )
    point_wgs84 = gpd.GeoSeries([point], crs=METRIC_CRS).to_crs("EPSG:4326").iloc[0]

    if index % 3 == 0:
        ppm = rng.uniform(5.2, 6.4)
    else:
        ppm = rng.uniform(7.0, 12.5)

    return {
        "observation_id": f"OBS-{index:04d}",
        "timestamp": _timestamp(rng, hours=96.0),
        "latitude": round(point_wgs84.y, 6),
        "longitude": round(point_wgs84.x, 6),
        "methane_concentration_ppm": round(ppm, 2),
        "wind_speed_kmh": round(WIND_SPEED_KMH + rng.uniform(-2, 2), 1),
        "wind_direction_deg": round(WIND_DIRECTION_DEG + rng.uniform(-8, 8), 1),
        "source_label": "Synthetic Pipeline Event",
        "is_anomaly": bool(ppm > OBSERVATION_THRESHOLD_PPM),
    }


def generate_observations() -> list[dict]:
    rng = random.Random(SEED)
    pipelines = gpd.read_file(PIPELINES_PATH)
    leaking = pipelines[pipelines["pipeline_id"].isin(LEAKING_PIPELINES)].copy()
    if set(leaking["pipeline_id"]) != set(LEAKING_PIPELINES):
        raise ValueError("The configured leaking pipeline IDs are missing from the pipeline dataset.")

    observations = [
        _background_observation(index, rng)
        for index in range(BACKGROUND_COUNT)
    ]
    next_index = BACKGROUND_COUNT
    for pipeline_id in LEAKING_PIPELINES:
        line = leaking.loc[leaking["pipeline_id"] == pipeline_id, "geometry"].iloc[0]
        projected_line = gpd.GeoSeries([line], crs=pipelines.crs or "EPSG:4326").to_crs(METRIC_CRS).iloc[0]
        for _ in range(PIPELINE_EVENT_COUNT):
            observations.append(_pipeline_event_observation(next_index, projected_line, rng))
            next_index += 1

    rng.shuffle(observations)
    return observations


def main() -> None:
    if not PIPELINES_PATH.exists():
        raise FileNotFoundError(f"Pipeline dataset not found: {PIPELINES_PATH}")
    if OBSERVATIONS_PATH.exists() and not BACKUP_PATH.exists():
        shutil.copy2(OBSERVATIONS_PATH, BACKUP_PATH)

    observations = generate_observations()
    with OBSERVATIONS_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=observations[0].keys())
        writer.writeheader()
        writer.writerows(observations)

    print(
        f"Generated {len(observations)} deterministic synthetic observations "
        f"({BACKGROUND_COUNT} background, {2 * PIPELINE_EVENT_COUNT} pipeline-event)."
    )
    print(f"Original observations preserved at {BACKUP_PATH}.")


if __name__ == "__main__":
    main()
