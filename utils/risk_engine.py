"""
risk_engine.py  --  MethaTrace Risk Engine + Weather Integration (Arnav's module)
 
*** IMPORTANT DISCLAIMER ***
The score produced here is a "Simulated Risk Score". It is a transparent,
rule-based number built for a college prototype demo. It is NOT a real-world
failure probability, NOT an engineering assessment, and must not be used for
any safety decision.
 
What this module does
---------------------
1. fetch_current_weather()  -> wind speed / wind direction / temperature for
                               Chakan, Pune from the free Open-Meteo API (no
                               API key). Falls back to mock data on ANY error.
2. calculate_risk_scores()  -> adds a 0-100 "Simulated Risk Score", a risk
                               level, a score breakdown and a plain-English
                               explanation to every pipeline segment.
 
How the score is built (max 100 points, all rules are visible below)
---------------------------------------------------------------------
    Operational status : 0-40 pts  operational attention indicator
    Methane            : 0-25 pts  strongest nearby usable anomaly
    Age                : 0-15 pts  older pipeline = more points
    Pressure           : 0-10 pts  prototype pressure-exposure heuristic
    Wind               : 0-10 pts  only counts when there IS a methane signal
 
Design notes
------------
* Pure numpy/pandas + the standard library. It does NOT require shapely or
  geopandas to be imported here; a GeoDataFrame works because it is a
  DataFrame subclass whose geometry column holds LineStrings (anything with a
  ``.coords`` attribute is accepted).
* Distances are computed with a simple flat-earth (equirectangular)
  approximation, which is accurate to well under 1% over a few km -- plenty
  for Chakan-sized areas and easy to explain.
"""
 
import json
import logging
import math
import urllib.parse
import urllib.request
import threading
import time
from datetime import datetime
 
import numpy as np
import pandas as pd
 
logger = logging.getLogger(__name__)
 
# ----------------------------------------------------------------------------
# CONFIGURATION -- every tunable number lives here so it is easy to explain
# ----------------------------------------------------------------------------
 
# Chakan, Pune
CHAKAN_LAT = 18.75
CHAKAN_LON = 73.81
 
# Open-Meteo "current weather" endpoint (free, no API key needed)
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_TIMEOUT_SECONDS = 5  # never let a slow API freeze the demo
WEATHER_CACHE_TTL_SECONDS = 600
WEATHER_FAILURE_COOLDOWN_SECONDS = 60
_weather_cache = {}
_weather_cache_lock = threading.Lock()


def _clear_weather_cache():
    """Clear cached weather; useful for deterministic tests and local tooling."""
    with _weather_cache_lock:
        _weather_cache.clear()
 
# Used when the API is unreachable or returns garbage.
# Wind direction follows the METEOROLOGICAL convention: the direction the
# wind blows FROM (270 = westerly wind, blowing towards the east).
FALLBACK_WEATHER = {
    "wind_speed_kmh": 10.0,
    "wind_direction_deg": 270.0,
    "temperature_c": 28.0,
}
 
# Score weights (these five add up to 100)
MAX_OPERATIONAL_POINTS = 40.0
MAX_METHANE_POINTS = 25.0
MAX_AGE_POINTS = 15.0
MAX_PRESSURE_POINTS = 10.0
MAX_WIND_POINTS = 10.0
 
# Methane rules
BACKGROUND_PPM = 2.0       # normal atmospheric methane is ~1.9 PPM -> 0 points
SATURATION_PPM = 10.0      # at or above this, methane earns the full 45 points
SEARCH_RADIUS_M = 500.0    # only readings within this distance count
 
# Age / pressure rules
AGE_SATURATION_YEARS = 30  # 30+ years old earns full age points
PRESSURE_SATURATION_BAR = 25.0  # 25+ bar earns full pressure points
 
# Risk level cut-offs
HIGH_THRESHOLD = 60
MEDIUM_THRESHOLD = 30
 
# Text that the UI should show next to the score
RISK_DISCLAIMER = (
    "Simulated Risk Score: a rule-based prototype value (0-100), "
    "not a real-world failure probability."
)
 
# Flat-earth conversion: metres per degree of latitude (close enough here)
_METRES_PER_DEG = 111_320.0
 
 
# ----------------------------------------------------------------------------
# 1. WEATHER INTEGRATION
# ----------------------------------------------------------------------------
def _fallback_weather(reason):
    """Return a copy of the mock weather, tagged so the UI can tell it is fake."""
    data = dict(FALLBACK_WEATHER)
    data["source"] = "fallback_mock"
    data["note"] = f"Live weather unavailable ({reason}); using default mock values."
    return data
 
 
def _fetch_current_weather(lat=CHAKAN_LAT, lon=CHAKAN_LON,
                           timeout=WEATHER_TIMEOUT_SECONDS):
    """
    Fetch current wind speed, wind direction and temperature from Open-Meteo.
 
    Returns a dict:
        {
          "wind_speed_kmh": float,
          "wind_direction_deg": float,   # direction wind comes FROM, 0-360
          "temperature_c": float,
          "source": "open-meteo" | "fallback_mock",
          "note": str                    # only explains a fallback
        }
 
    This function NEVER raises. Any problem (no internet, timeout, bad JSON,
    missing keys, nonsense values) returns the fallback mock data instead, so
    the dashboard cannot crash because of the weather.
    """
    try:
        params = urllib.parse.urlencode({
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,wind_speed_10m,wind_direction_10m",
            "wind_speed_unit": "kmh",
        })
        url = f"{OPEN_METEO_URL}?{params}"
 
        with urllib.request.urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
 
        current = payload["current"]  # KeyError if the API shape changes
        speed = float(current["wind_speed_10m"])
        direction = float(current["wind_direction_10m"])
        temperature = float(current["temperature_2m"])
 
        # Sanity-check the numbers (NaN/inf/negative speed => treat as failure)
        if not all(math.isfinite(v) for v in (speed, direction, temperature)):
            raise ValueError("non-finite value in weather response")
        if speed < 0:
            raise ValueError("negative wind speed in weather response")
 
        return {
            "wind_speed_kmh": speed,
            "wind_direction_deg": direction % 360.0,
            "temperature_c": temperature,
            "source": "open-meteo",
            "note": "",
        }
 
    except Exception as exc:  # deliberately broad: the demo must never crash
        logger.warning("Weather fetch failed (%s: %s); using fallback.",
                       type(exc).__name__, exc)
        return _fallback_weather(type(exc).__name__)


def fetch_current_weather(lat=CHAKAN_LAT, lon=CHAKAN_LON,
                          timeout=WEATHER_TIMEOUT_SECONDS):
    """Return cached weather when fresh; reuse the last live result on failure.

    Successful provider values are cached for ten minutes. Failed requests are
    cooled down for one minute to avoid hammering the provider during an outage
    or HTTP 429 response. The previous live value wins over mock fallback data.
    """
    key = (round(float(lat), 4), round(float(lon), 4))
    now = time.monotonic()
    with _weather_cache_lock:
        cached = _weather_cache.get(key)
        if cached:
            age = now - cached["fetched_at"]
            if cached["data"].get("source") == "open-meteo" and age < WEATHER_CACHE_TTL_SECONDS:
                return dict(cached["data"])
            if now - cached["last_attempt"] < WEATHER_FAILURE_COOLDOWN_SECONDS:
                return dict(cached["data"])

        result = _fetch_current_weather(lat=lat, lon=lon, timeout=timeout)
        if result.get("source") == "open-meteo":
            _weather_cache[key] = {
                "data": dict(result), "fetched_at": now, "last_attempt": now,
            }
            return dict(result)

        if cached and cached["data"].get("source") == "open-meteo":
            stale = dict(cached["data"])
            stale["note"] = f"Live weather refresh failed; reusing last successful result. {result.get('note', '')}".strip()
            cached["last_attempt"] = now
            return stale

        _weather_cache[key] = {
            "data": dict(result), "fetched_at": now, "last_attempt": now,
        }
        return dict(result)
 
 
# ----------------------------------------------------------------------------
# GEOMETRY HELPERS (small, dependency-free)
# ----------------------------------------------------------------------------
def _to_local_metres(lons, lats):
    """Convert lon/lat degrees to local x/y metres around Chakan."""
    lons = np.asarray(lons, dtype=float)
    lats = np.asarray(lats, dtype=float)
    x = (lons - CHAKAN_LON) * _METRES_PER_DEG * math.cos(math.radians(CHAKAN_LAT))
    y = (lats - CHAKAN_LAT) * _METRES_PER_DEG
    return x, y
 
 
def _line_vertices(geometry):
    """
    Return the (lon, lat) vertices of a LineString as an (N, 2) array.
    Also tolerates a Multi-part geometry by joining all its parts' vertices.
    Returns None if the geometry is missing/empty.
    """
    if geometry is None:
        return None
    if hasattr(geometry, "geoms"):  # MultiLineString
        coords = [c for part in geometry.geoms for c in part.coords]
    elif hasattr(geometry, "coords"):  # LineString
        coords = list(geometry.coords)
    else:
        return None
    if len(coords) < 2:
        return None
    return np.array([(c[0], c[1]) for c in coords], dtype=float)
 
 
def _nearest_point_on_line(vertices_xy, px, py):
    """
    For each point (px[i], py[i]) find the closest point on the polyline.
 
    vertices_xy : (N, 2) array of local-metre coordinates
    Returns (distance_m, nearest_x, nearest_y), each an array like px.
    """
    best_d = np.full(px.shape, np.inf)
    best_x = np.zeros(px.shape)
    best_y = np.zeros(px.shape)
 
    for i in range(len(vertices_xy) - 1):
        ax, ay = vertices_xy[i]
        bx, by = vertices_xy[i + 1]
        abx, aby = bx - ax, by - ay
        seg_len_sq = abx * abx + aby * aby
 
        if seg_len_sq == 0:
            t = np.zeros(px.shape)  # zero-length segment: nearest is the vertex
        else:
            # Project the point onto the segment, clamp to [0, 1]
            t = ((px - ax) * abx + (py - ay) * aby) / seg_len_sq
            t = np.clip(t, 0.0, 1.0)
 
        cx = ax + t * abx
        cy = ay + t * aby
        d = np.hypot(px - cx, py - cy)
 
        closer = d < best_d
        best_d = np.where(closer, d, best_d)
        best_x = np.where(closer, cx, best_x)
        best_y = np.where(closer, cy, best_y)
 
    return best_d, best_x, best_y
 
 
def _angle_difference(a_deg, b_deg):
    """Smallest absolute angle between two compass bearings (0-180)."""
    return np.abs((np.asarray(a_deg) - b_deg + 180.0) % 360.0 - 180.0)
 
 
# ----------------------------------------------------------------------------
# SCORING RULES (each returns points, so the breakdown is easy to explain)
# ----------------------------------------------------------------------------
def _methane_fraction(ppm):
    """0..1 : how far above background the reading is (1 = saturated)."""
    return np.clip((ppm - BACKGROUND_PPM) / (SATURATION_PPM - BACKGROUND_PPM), 0.0, 1.0)
 
 
def _age_points(installed_year, reference_year):
    """Older pipeline -> more points. Missing data is unavailable."""
    if pd.isna(installed_year):
        return None, None
    age = max(0, reference_year - int(installed_year))
    return MAX_AGE_POINTS * min(age / AGE_SATURATION_YEARS, 1.0), age
 
 
def _pressure_points(pressure_bar):
    """Prototype pressure-exposure heuristic; missing data is unavailable."""
    if pd.isna(pressure_bar) or float(pressure_bar) < 0:
        return None
    frac = min(float(pressure_bar) / PRESSURE_SATURATION_BAR, 1.0)
    return MAX_PRESSURE_POINTS * frac


def _operational_points(status):
    """Operational attention points, not evidence of physical danger."""
    if status is None or pd.isna(status):
        return None
    return {
        "active": 0.0,
        "maintenance": 15.0,
        "leaking": 40.0,
    }.get(str(status).strip().lower())


def _usable_number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
 
 
def _wind_alignment(obs_bearing_deg, wind_from_deg):
    """
    0.2 .. 1.0 : how much the wind links the pipeline to the reading.
 
    obs_bearing_deg : compass bearing from the pipeline TO the reading.
    wind_from_deg   : direction the wind blows FROM (meteorological).
 
    The wind carries gas towards (wind_from + 180). If the reading sits in that
    direction it is DOWNWIND of the pipeline  -> 1.0
    Crosswind                                  -> 0.6
    UPWIND (gas arriving from elsewhere)       -> 0.2
    """
    wind_to = (wind_from_deg + 180.0) % 360.0
    diff = float(_angle_difference(obs_bearing_deg, wind_to))
    return 0.6 + 0.4 * math.cos(math.radians(diff)), diff
 
 
def _position_word(diff_deg):
    """Turn the bearing difference into a human word."""
    if diff_deg <= 45:
        return "downwind"
    if diff_deg >= 135:
        return "upwind"
    return "crosswind"
 
 
def _risk_level(score):
    if score >= HIGH_THRESHOLD:
        return "High"
    if score >= MEDIUM_THRESHOLD:
        return "Medium"
    return "Low"
 
 
# ----------------------------------------------------------------------------
# 2 + 3 + 4. RISK SCORING WITH EXPLANATIONS
# ----------------------------------------------------------------------------
def _legacy_calculate_risk_scores(pipelines, observations, weather=None, reference_year=None):
    """
    Add a "Simulated Risk Score" and an explanation to every pipeline segment.
 
    Parameters
    ----------
    pipelines : GeoDataFrame (or DataFrame) with columns
        geometry (LineString, EPSG:4326), pipeline_id, pressure_bar, installed
    observations : DataFrame with columns
        latitude, longitude, methane_concentration_ppm, is_ml_anomaly
        (only rows with is_ml_anomaly == True are used)
    weather : dict from fetch_current_weather(); fetched automatically if None
    reference_year : year used to compute pipeline age (default: current year;
        pass a fixed year in tests so results never change)
 
    Returns
    -------
    A COPY of `pipelines` (original is untouched) with these new columns:
        simulated_risk_score  float 0-100  (label this "Simulated Risk Score")
        risk_level            "Low" | "Medium" | "High"
        risk_explanation      short plain-English reason
        score_methane / score_age / score_pressure / score_wind
                              the four components that add up to the score
    plus the weather used is stored in result.attrs["weather"] and the
    disclaimer text in result.attrs["disclaimer"].
    """
    # --- 0. Validate inputs (clear errors beat mysterious KeyErrors) --------
    required_pipe_cols = {"geometry", "pipeline_id", "pressure_bar", "installed"}
    required_obs_cols = {"latitude", "longitude",
                         "methane_concentration_ppm", "is_ml_anomaly"}
    missing_p = required_pipe_cols - set(pipelines.columns)
    missing_o = required_obs_cols - set(observations.columns)
    if missing_p:
        raise ValueError(f"pipelines is missing columns: {sorted(missing_p)}")
    if missing_o:
        raise ValueError(f"observations is missing columns: {sorted(missing_o)}")
 
    if weather is None:
        weather = fetch_current_weather()
    if reference_year is None:
        reference_year = datetime.now().year
 
    wind_from = float(weather["wind_direction_deg"])
    wind_speed = float(weather["wind_speed_kmh"])
 
    # --- 1. Keep only usable ML-flagged observations ------------------------
    obs = observations.copy()
    obs["is_ml_anomaly"] = obs["is_ml_anomaly"].astype(bool)
    obs = obs[obs["is_ml_anomaly"]]
    obs = obs.dropna(subset=["latitude", "longitude", "methane_concentration_ppm"])
 
    obs_x, obs_y = _to_local_metres(obs["longitude"].to_numpy(),
                                    obs["latitude"].to_numpy())
    obs_ppm = obs["methane_concentration_ppm"].to_numpy(dtype=float)
 
    # --- 2. Score each pipeline ---------------------------------------------
    scores, levels, explanations = [], [], []
    comp_methane, comp_age, comp_pressure, comp_wind = [], [], [], []
 
    for _, row in pipelines.iterrows():
        # ---- methane component: find the strongest nearby reading ----------
        methane_frac = 0.0
        best = None  # details of the strongest nearby reading
 
        vertices = _line_vertices(row["geometry"])
        if vertices is not None and len(obs_ppm) > 0:
            vx, vy = _to_local_metres(vertices[:, 0], vertices[:, 1])
            line_xy = np.column_stack([vx, vy])
            dist, near_x, near_y = _nearest_point_on_line(line_xy, obs_x, obs_y)
 
            # Signal = how high the PPM is  x  how close the reading is
            closeness = np.clip(1.0 - dist / SEARCH_RADIUS_M, 0.0, 1.0)
            signal = _methane_fraction(obs_ppm) * closeness
 
            if signal.max() > 0:
                k = int(np.argmax(signal))
                methane_frac = float(signal[k])
                # compass bearing from the nearest pipeline point to the reading
                bearing = math.degrees(math.atan2(obs_x[k] - near_x[k],
                                                  obs_y[k] - near_y[k])) % 360.0
                best = {"ppm": float(obs_ppm[k]), "dist": float(dist[k]),
                        "bearing": bearing}
 
        methane_pts = MAX_METHANE_POINTS * methane_frac
 
        # ---- wind component (only meaningful if a methane signal exists) ---
        wind_pts = 0.0
        position = None
        if best is not None:
            alignment, diff = _wind_alignment(best["bearing"], wind_from)
            wind_pts = MAX_WIND_POINTS * alignment * methane_frac
            position = _position_word(diff)
 
        # ---- age and pressure components -----------------------------------
        age_pts, age_years = _age_points(row["installed"], reference_year)
        pressure_pts = _pressure_points(row["pressure_bar"])
 
        total = float(np.clip(methane_pts + age_pts + pressure_pts + wind_pts,
                              0.0, 100.0))
        level = _risk_level(total)
 
        # ---- explanation string --------------------------------------------
        if best is not None:
            methane_txt = (f"{best['ppm']:.1f} PPM methane detected "
                           f"{best['dist']:.0f}m {position}")
        else:
            methane_txt = f"no ML-flagged methane within {SEARCH_RADIUS_M:.0f}m"
 
        if age_years is not None:
            age_txt = f"installed {int(row['installed'])} ({age_years} yrs old)"
        else:
            age_txt = "install year unknown"
 
        pressure_txt = ("pressure unknown" if pd.isna(row["pressure_bar"])
                        else f"{float(row['pressure_bar']):.1f} bar")
 
        explanation = (f"{level} Risk (Simulated {total:.0f}/100): {methane_txt}; "
                       f"{age_txt}; {pressure_txt}; "
                       f"wind from {wind_from:.0f}\u00b0 at {wind_speed:.0f} km/h.")
 
        scores.append(round(total, 1))
        levels.append(level)
        explanations.append(explanation)
        comp_methane.append(round(methane_pts, 1))
        comp_age.append(round(age_pts, 1))
        comp_pressure.append(round(pressure_pts, 1))
        comp_wind.append(round(wind_pts, 1))
 
    # --- 3. Attach results to a copy of the pipelines ------------------------
    result = pipelines.copy()
    result["simulated_risk_score"] = scores
    result["risk_level"] = levels
    result["risk_explanation"] = explanations
    result["score_methane"] = comp_methane
    result["score_age"] = comp_age
    result["score_pressure"] = comp_pressure
    result["score_wind"] = comp_wind
    result.attrs["weather"] = weather
    result.attrs["disclaimer"] = RISK_DISCLAIMER
    return result


def calculate_risk_scores(pipelines, observations, weather=None, reference_year=None):
    """Calculate the simulated five-component Pipeline Risk Priority Index."""
    required_pipe_cols = {"geometry", "pipeline_id", "pressure_bar", "installed"}
    required_obs_cols = {
        "latitude", "longitude", "methane_concentration_ppm",
    }
    missing_p = required_pipe_cols - set(pipelines.columns)
    if missing_p:
        raise ValueError(f"pipelines is missing columns: {sorted(missing_p)}")
    observations_missing = observations is None
    if observations_missing:
        observations = pd.DataFrame(columns=list(required_obs_cols))
    missing_o = required_obs_cols - set(observations.columns)
    if missing_o:
        raise ValueError(f"observations is missing columns: {sorted(missing_o)}")
    if weather is None:
        weather = fetch_current_weather()
    if reference_year is None:
        reference_year = datetime.now().year

    wind_from = _usable_number(weather.get("wind_direction_deg"))
    wind_speed = _usable_number(weather.get("wind_speed_kmh"))
    weather_available = (
        wind_from is not None and wind_speed is not None and wind_speed >= 0
    )
    obs = observations.copy()
    flags_available = {"is_ml_anomaly", "is_threshold_anomaly"} <= set(obs.columns)
    usable = obs[["latitude", "longitude", "methane_concentration_ppm"]].notna().all(axis=1)
    obs_available = not observations_missing and flags_available and not obs.loc[
        usable, ["is_ml_anomaly", "is_threshold_anomaly"]
    ].isna().any().any()
    obs = obs[usable].copy()
    if obs_available:
        obs["is_ml_anomaly"] = obs["is_ml_anomaly"].astype(bool)
        obs["is_threshold_anomaly"] = obs["is_threshold_anomaly"].astype(bool)
        obs = obs[obs["is_ml_anomaly"] | obs["is_threshold_anomaly"]]
    else:
        obs = obs.iloc[0:0]
    if obs_available and not obs.empty:
        obs_x, obs_y = _to_local_metres(
            obs["longitude"].to_numpy(), obs["latitude"].to_numpy()
        )
        obs_ppm = obs["methane_concentration_ppm"].to_numpy(dtype=float)

    scores, levels, explanations = [], [], []
    component_values = {key: [] for key in (
        "operational", "methane", "age", "pressure", "wind"
    )}
    component_available = {key: [] for key in component_values}
    maxima = {
        "operational": MAX_OPERATIONAL_POINTS,
        "methane": MAX_METHANE_POINTS,
        "age": MAX_AGE_POINTS,
        "pressure": MAX_PRESSURE_POINTS,
        "wind": MAX_WIND_POINTS,
    }
    names = {
        "operational": "Operational status",
        "methane": "Methane observations",
        "age": "Pipeline age",
        "pressure": "Rated pressure",
        "wind": "Wind conditions",
    }
    scored_maximums, qualities, missing_lists = [], [], []

    for _, row in pipelines.iterrows():
        operational_pts = _operational_points(row.get("status"))
        methane_fraction = None if not obs_available else 0.0
        best = None
        vertices = _line_vertices(row["geometry"])
        if obs_available and vertices is not None and not obs.empty:
            vx, vy = _to_local_metres(vertices[:, 0], vertices[:, 1])
            dist, near_x, near_y = _nearest_point_on_line(
                np.column_stack([vx, vy]), obs_x, obs_y
            )
            closeness = np.clip(1.0 - dist / SEARCH_RADIUS_M, 0.0, 1.0)
            multiplier = np.where(
                obs["is_ml_anomaly"].to_numpy(), 1.0, 0.75
            )
            signal = _methane_fraction(obs_ppm) * closeness * multiplier
            if signal.max() > 0:
                index = int(np.argmax(signal))
                methane_fraction = float(signal[index])
                bearing = math.degrees(math.atan2(
                    obs_x[index] - near_x[index],
                    obs_y[index] - near_y[index],
                )) % 360.0
                best = {
                    "ppm": float(obs_ppm[index]),
                    "dist": float(dist[index]),
                    "bearing": bearing,
                }

        methane_pts = (
            None if methane_fraction is None
            else MAX_METHANE_POINTS * methane_fraction
        )
        wind_pts = None if not weather_available else 0.0
        position = None
        if best is not None and weather_available:
            alignment, diff = _wind_alignment(best["bearing"], wind_from)
            wind_pts = MAX_WIND_POINTS * alignment * methane_fraction
            position = _position_word(diff)
        age_pts, age_years = _age_points(row["installed"], reference_year)
        pressure_pts = _pressure_points(row["pressure_bar"])
        values = {
            "operational": operational_pts,
            "methane": methane_pts,
            "age": age_pts,
            "pressure": pressure_pts,
            "wind": wind_pts,
        }
        missing = [names[key] for key, value in values.items() if value is None]
        total = round(sum(value for value in values.values() if value is not None), 1)
        scored_maximum = sum(
            maxima[key] for key, value in values.items() if value is not None
        )
        level = _risk_level(total) if not missing else "Incomplete"
        methane_text = (
            f"{best['ppm']:.1f} PPM methane detected {best['dist']:.0f}m {position}"
            if best is not None
            else f"no usable methane anomaly within {SEARCH_RADIUS_M:.0f}m"
        )
        age_text = (
            f"installed {int(row['installed'])} ({age_years} yrs old)"
            if age_years is not None else "install year unavailable"
        )
        pressure_text = (
            f"{float(row['pressure_bar']):.1f} bar"
            if pressure_pts is not None else "pressure unavailable"
        )
        explanation = (
            f"{level} Risk Priority Index (Simulated): {methane_text}; "
            f"{age_text}; {pressure_text}; "
            f"wind from {wind_from:.0f}\N{DEGREE SIGN} at {wind_speed:.0f} km/h."
            if weather_available else
            f"{level} Risk Priority Index (Simulated): {methane_text}; "
            f"{age_text}; {pressure_text}; wind unavailable."
        )
        scores.append(total)
        levels.append(level)
        explanations.append(explanation)
        for key, value in values.items():
            component_values[key].append(
                None if value is None else round(value, 1)
            )
            component_available[key].append(value is not None)
        scored_maximums.append(scored_maximum)
        qualities.append("complete" if not missing else "incomplete")
        missing_lists.append(missing)

    result = pipelines.copy()
    result["simulated_risk_score"] = scores
    result["risk_level"] = levels
    result["risk_explanation"] = explanations
    for key in component_values:
        result[f"score_{key}"] = component_values[key]
        result[f"score_{key}_available"] = component_available[key]
    result["scored_maximum"] = scored_maximums
    result["data_quality"] = qualities
    result["missing_factors"] = missing_lists
    result.attrs["weather"] = weather
    result.attrs["disclaimer"] = RISK_DISCLAIMER
    return result


def assess_pipeline_risk(
    pipeline: dict,
    observations: pd.DataFrame,
    sensor_reading: dict = None,
    weather: dict = None,
) -> dict:
    """
    Adapt the existing fleet risk engine for one selected pipeline.

    Returns a structured result for utils.integrations.
    """

    from shapely.geometry import LineString

    geometry = pipeline.get("geometry")
    if geometry is None:
        start = pipeline.get("start_coords")
        end = pipeline.get("end_coords")

        if not start or not end:
            raise ValueError("Pipeline start/end coordinates are unavailable.")

        # Dashboard coordinates are (latitude, longitude).
        # Shapely expects (longitude, latitude).
        geometry = LineString([
            (start[1], start[0]),
            (end[1], end[0]),
        ])

    installed = pipeline.get("installation_year")
    if installed is None:
        installed = pipeline.get("installed")

    single_pipeline = pd.DataFrame([{
        "pipeline_id": pipeline["pipeline_id"],
        "geometry": geometry,
        "status": pipeline.get("status"),
        "pressure_bar": pipeline.get("pressure_bar"),
        "installed": installed,
    }])

    result = calculate_risk_scores(
        single_pipeline,
        observations,
        weather=weather,
    )

    row = result.iloc[0]
    weather_used = result.attrs.get("weather", {})
    factor_specs = [
        ("Operational status", "operational", MAX_OPERATIONAL_POINTS),
        ("Methane observations", "methane", MAX_METHANE_POINTS),
        ("Pipeline age", "age", MAX_AGE_POINTS),
        ("Rated pressure", "pressure", MAX_PRESSURE_POINTS),
        ("Wind conditions", "wind", MAX_WIND_POINTS),
    ]
    explanations = {
        "operational": (
            f"Operational status is {pipeline.get('status')}."
            if row["score_operational_available"]
            else "Operational status unavailable."
        ),
        "methane": (
            f"{row['score_methane']:.1f}/{MAX_METHANE_POINTS:g} points from the strongest usable nearby methane anomaly."
            if row["score_methane_available"] and row["score_methane"] > 0
            else (
                f"No usable methane anomalies within {SEARCH_RADIUS_M:.0f}m."
                if row["score_methane_available"]
                else "Observation anomaly classification unavailable."
            )
        ),
        "age": (
            f"{row['score_age']:.1f}/{MAX_AGE_POINTS:g} points from pipeline age."
            if row["score_age_available"]
            else "Install year unavailable."
        ),
        "pressure": (
            f"{row['score_pressure']:.1f}/{MAX_PRESSURE_POINTS:g} points from rated pressure; prototype pressure-exposure heuristic."
            if row["score_pressure_available"]
            else "Rated pressure unavailable."
        ),
        "wind": (
            f"{row['score_wind']:.1f}/{MAX_WIND_POINTS:g} points from wind alignment."
            if row["score_wind_available"] and row["score_wind"] > 0
            else (
                "No methane signal to associate with wind."
                if row["score_wind_available"]
                else "Wind data unavailable."
            )
        ),
    }
    methane_explanation = (
        f"{row['score_methane']:.1f}/{MAX_METHANE_POINTS:g} points from nearby methane."
        if row["score_methane_available"] and row["score_methane"] > 0
        else f"No usable methane anomaly within {SEARCH_RADIUS_M:.0f}m."
    )
    age_explanation = (
        f"{row['score_age']:.1f}/{MAX_AGE_POINTS:g} points from pipeline age."
        if row["score_age_available"]
        else "Install year unavailable; no age points."
    )
    pressure_explanation = (
        f"{row['score_pressure']:.1f}/{MAX_PRESSURE_POINTS:g} points from rated pressure."
        if row["score_pressure_available"]
        else "Rated pressure unavailable; no pressure points."
    )
    wind_explanation = (
        f"{row['score_wind']:.1f}/{MAX_WIND_POINTS:g} points from wind alignment with the methane signal."
        if row["score_wind_available"] and row["score_wind"] > 0
        else "No wind points because there is no usable ML methane signal."
    )

    factor_breakdown = [
        {
            "name": name,
            "score": None if not row[f"score_{key}_available"] else round(float(row[f"score_{key}"]), 1),
            "maximum": maximum,
            "available": bool(row[f"score_{key}_available"]),
            "explanation": explanations[key],
        }
        for name, key, maximum in factor_specs
    ]

    factors = [
        f"Operational status contribution: {row['score_operational'] if row['score_operational_available'] else 'unavailable'}/40",
        f"Methane contribution: {row['score_methane'] if row['score_methane_available'] else 'unavailable'}/25",
        f"Pipeline age contribution: {row['score_age'] if row['score_age_available'] else 'unavailable'}/15",
        f"Pressure contribution: {row['score_pressure'] if row['score_pressure_available'] else 'unavailable'}/10",
        f"Wind contribution: {row['score_wind'] if row['score_wind_available'] else 'unavailable'}/10",
        row["risk_explanation"],
    ]

    return {
        "score": float(row["simulated_risk_score"]),
        "level": str(row["risk_level"]),
        "factors": factors,
        "factor_breakdown": factor_breakdown,
        "weather": dict(weather_used),
        "scored_maximum": int(row["scored_maximum"]),
        "data_quality": str(row["data_quality"]),
        "missing_factors": list(row["missing_factors"]),
    }
