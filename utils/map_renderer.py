"""
map_renderer.py  --  MethaTrace cinematic 3D command-center map (pydeck / deck.gl)

    deck = render_pipeline_map(pipelines_gdf, observations_df)
    st.pydeck_chart(deck, width='stretch')

render_pipeline_map() RETURNS a pydeck.Deck; it does not draw anything itself.

Layer stack (bottom -> top)
---------------------------
    1. Laser geofence          PolygonLayer      blacked-out ground + 4px neon edge
    2. Toxic ground-glow       HeatmapLayer      soft radioactive haze from methane
    3. Procedural skyline      PolygonLayer 3D   matte-black blocks, cyan wireframe
    4. Pipeline bloom          GeoJsonLayer      wide, translucent glow
    5. Pipeline core           GeoJsonLayer      thin, solid, hover-able
    6. Methane hex-matrix      HexagonLayer 3D   spikes with PPM
    7. Trajectory arcs         ArcLayer          anomalies -> downwind, into the sky
    8. IoT node halos + cores  ScatterplotLayer  (x2) at pipeline intersections
    9. SCADA labels            TextLayer         data-driven status per zone

GLITCH-PROOFING RULE: every width / radius below is set in PIXELS explicitly
(line_width_units / width_units / radius_units = "pixels"). Nothing relies on
deck.gl's default of metres, so lines cannot balloon when the camera moves.

Data notes
----------
* Pipelines: any DataFrame/GeoDataFrame with a LineString `geometry` column in
  EPSG:4326 (only `.coords` is read). If the risk engine has been run
  (`risk_level`, `simulated_risk_score`, `risk_explanation`), pipelines are
  coloured by risk; otherwise by `status`.
* Observations: needs latitude, longitude, methane_concentration_ppm; uses
  is_ml_anomaly (or is_anomaly) when present to choose arc sources.
* All map coordinates are real lon/lat in the Chakan area. The skyline is
  PROCEDURAL scenery, not surveyed building footprints.
"""

import html
import math
import random

import numpy as np
import pandas as pd
import pydeck as pdk

# ----------------------------------------------------------------------------
# CONFIGURATION
# ----------------------------------------------------------------------------

# --- Camera (cinematic, tightly limited) ------------------------------------
CAMERA_LAT, CAMERA_LON = 18.76, 73.81
CAMERA_ZOOM = 14
CAMERA_PITCH = 75
CAMERA_BEARING = 45
MIN_ZOOM, MAX_ZOOM = 13.5, 14.5     # user can only nudge zoom inside this band
# deck.gl's MapView caps pitch at 60 unless max_pitch is raised -> required
# for the 75-degree angle to actually apply.
MIN_PITCH, MAX_PITCH = 60, 85

# --- Geofence (Chakan MIDC, per project brief) -------------------------------
GEOFENCE_LAT_MIN, GEOFENCE_LAT_MAX = 18.73, 18.80
GEOFENCE_LON_MIN, GEOFENCE_LON_MAX = 73.78, 73.85

# --- Palette -----------------------------------------------------------------
CYAN = [0, 240, 255]
GOLD = [255, 200, 0]
CRIMSON = [255, 20, 70]

# --- Shared 3D material: polished metal + neon specular ----------------------
# Applied to every extruded layer (skyline + hexagons). Flat layers (lines,
# circles, text, arcs, heatmap) are not lit by deck.gl, so they ignore it.
MATERIAL = {
    "ambient": 0.35,
    "diffuse": 0.60,
    "shininess": 96,
    "specularColor": [120, 230, 255],
}

# --- Methane hex-matrix --------------------------------------------------------
HEX_COLOR_RANGE = [
    [18, 10, 70],     # deep indigo
    [40, 60, 220],    # electric blue
    [0, 230, 255],    # cyan
    [255, 214, 10],   # glowing gold
    [255, 60, 120],   # hot pink-red
    [255, 0, 80],     # neon crimson
]
BACKGROUND_PPM = 2.0      # ~ normal atmosphere: bottom of colour + height scale
SATURATION_PPM = 12.0     # top of colour + height scale
HEX_RADIUS_M = 90         # hexagon radius in metres (right size for zoom 14)
HEX_HEIGHT_RANGE_M = [15, 800]   # flat slab -> aggressive spike

# --- Ground glow ---------------------------------------------------------------
HEATMAP_RADIUS_PX = 140
HEATMAP_COLOR_RANGE = [
    [0, 60, 30, 0],
    [0, 170, 90, 70],
    [120, 255, 0, 130],
    [220, 255, 0, 180],
    [255, 200, 0, 215],
    [255, 80, 0, 240],
]

# --- Wind / arcs -----------------------------------------------------------------
ARC_COUNT = 6
DEFAULT_WIND_FROM_DEG = 225   # south-westerly wind -> blows north-east
ARC_MIN_LENGTH_M = 900
ARC_LENGTH_PER_PPM_M = 150
ARC_HEIGHT_FACTOR = 2.5       # bigger = arcs climb higher into the sky

# --- Procedural skyline ------------------------------------------------------------
SKYLINE_COLS, SKYLINE_ROWS = 8, 6      # 48 candidate plots ...
SKYLINE_MAX_BUILDINGS = 30             # ... the 30 clearest of pipelines are used
SKYLINE_PITCH_M = (230.0, 210.0)       # plot spacing (east-west, north-south)
SKYLINE_HEIGHT_M = (30, 150)
SKYLINE_SEED = 42                      # fixed seed -> same skyline every rerun

# --- SCADA zones -----------------------------------------------------------------------
# !! APPROXIMATE, SCHEMATIC POSITIONS !! Placed near the camera centre so they
# are visible in the locked frame. NOT surveyed; replace with verified
# coordinates before presenting them as real plant locations.  (name, lat, lon)
SCADA_ZONES = [
    ("TATA MOTORS",  18.7640, 73.8040),
    ("MAHINDRA",     18.7560, 73.8180),
    ("BAJAJ",        18.7660, 73.8170),
    ("MIDC PHASE 2", 18.7550, 73.8030),
]
ZONE_RADIUS_M = 1500       # anomalies within this distance set a zone's status
ZONE_ALERT_PPM = 8.0
ZONE_ELEVATED_PPM = 5.0
LABEL_ALTITUDE_M = 260     # labels float above the skyline

# --- IoT nodes ------------------------------------------------------------------------------
MAX_IOT_NODES = 40
MAX_SEGMENTS_FOR_INTERSECTION = 1500   # keeps the O(n^2) maths fast

_M_PER_DEG = 111_320.0

# --- Tooltip (military-style HUD with neon border) -----------------------------------------
TOOLTIP = {
    "html": (
        '<div style="color:#00f0ff;font-weight:700;letter-spacing:2px;'
        'border-bottom:1px solid rgba(0,240,255,0.4);padding-bottom:4px;">'
        "{tooltip_title}</div>"
        '<div style="margin-top:6px;line-height:1.5;">{tooltip_body}</div>'
    ),
    "style": {
        "backgroundColor": "rgba(3, 6, 18, 0.94)",
        "border": "1px solid #00f0ff",
        "boxShadow": "0 0 14px rgba(0,240,255,0.55), inset 0 0 10px rgba(0,240,255,0.15)",
        "borderRadius": "2px",
        "color": "#bfefff",
        "fontFamily": "Courier New, monospace",
        "fontSize": "12px",
        "padding": "10px 12px",
        "maxWidth": "340px",
    },
}


# ----------------------------------------------------------------------------
# GEOMETRY HELPERS
# ----------------------------------------------------------------------------
def _offset_to_lonlat(lat0, lon0, dx_m, dy_m):
    """Move dx metres east / dy metres north from (lat0, lon0)."""
    lat = lat0 + dy_m / _M_PER_DEG
    lon = lon0 + dx_m / (_M_PER_DEG * math.cos(math.radians(lat0)))
    return lon, lat


def _geometry_to_paths(geometry):
    """LineString / MultiLineString -> list of [[lon, lat], ...] paths."""
    if geometry is None:
        return []
    parts = list(geometry.geoms) if hasattr(geometry, "geoms") else [geometry]
    paths = []
    for part in parts:
        if not hasattr(part, "coords"):
            continue
        coords = [[float(c[0]), float(c[1])] for c in part.coords]
        if len(coords) >= 2:
            paths.append(coords)
    return paths


def _geofence_ring():
    """Closed rectangle of [lon, lat] points."""
    return [
        [GEOFENCE_LON_MIN, GEOFENCE_LAT_MIN],
        [GEOFENCE_LON_MAX, GEOFENCE_LAT_MIN],
        [GEOFENCE_LON_MAX, GEOFENCE_LAT_MAX],
        [GEOFENCE_LON_MIN, GEOFENCE_LAT_MAX],
        [GEOFENCE_LON_MIN, GEOFENCE_LAT_MIN],
    ]


def _esc(value):
    """HTML-escape text before it goes into a tooltip."""
    return html.escape(str(value))


# ----------------------------------------------------------------------------
# DATA PREPARATION
# ----------------------------------------------------------------------------
def _clean_observations(observations_df):
    """Keep only rows with usable lat / lon / ppm, as numeric columns."""
    needed = ["latitude", "longitude", "methane_concentration_ppm"]
    missing = set(needed) - set(observations_df.columns)
    if missing:
        raise ValueError(f"observations_df is missing columns: {sorted(missing)}")
    df = observations_df.copy()
    for col in needed:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=needed)


def _flagged(obs):
    """Anomaly rows (ML flag preferred, raw flag second, else every row)."""
    for flag in ("is_ml_anomaly", "is_anomaly"):
        if flag in obs.columns:
            return obs[obs[flag].astype(bool)]
    return obs


def _pipeline_colors(row):
    """(core_rgba, bloom_rgba) for a pipeline: risk_level first, then status."""
    level = row.get("risk_level")
    if level is None or pd.isna(level):
        status = row.get("status")
        level = {"Leaking": "High", "Maintenance": "Medium"}.get(status, "Low")
    rgb = {"High": CRIMSON, "Medium": GOLD}.get(level, CYAN)
    return rgb + [255], rgb + [55]


def _pipeline_features(pipelines_gdf):
    """
    GeoJSON FeatureCollection for the two pipeline layers. Each feature carries
    its colours and tooltip text, both inside `properties` and at the top level
    (so hover works however pydeck resolves tooltip fields).
    """
    features = []
    for _, row in pipelines_gdf.iterrows():
        core, bloom = _pipeline_colors(row)
        title = f"PIPELINE // {_esc(row.get('pipeline_id', 'UNKNOWN'))}"
        lines = []
        for key, label in (("type", "TYPE"), ("status", "STATUS")):
            if key in row and pd.notna(row[key]):
                lines.append(f"{label}: {_esc(row[key])}")
        if "simulated_risk_score" in row and pd.notna(row["simulated_risk_score"]):
            lines.append(f"SIMULATED RISK SCORE: {float(row['simulated_risk_score']):.0f}/100")
        if isinstance(row.get("risk_explanation"), str):
            lines.append(_esc(row["risk_explanation"]))
        body = "<br/>".join(lines) if lines else "NO TELEMETRY"

        for path in _geometry_to_paths(row["geometry"]):
            props = {"core_color": core, "bloom_color": bloom,
                     "tooltip_title": title, "tooltip_body": body}
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": path},
                "properties": props,
                "tooltip_title": title,
                "tooltip_body": body,
            })
    return {"type": "FeatureCollection", "features": features}


def _sample_points(features, step_deg=0.00025):
    """Densify every pipeline path (~25 m spacing) into an (N, 2) lon/lat array."""
    pts = []
    for f in features:
        coords = f["geometry"]["coordinates"]
        for (x1, y1), (x2, y2) in zip(coords[:-1], coords[1:]):
            n = max(int(math.hypot(x2 - x1, y2 - y1) / step_deg), 1)
            for k in range(n + 1):
                t = k / n
                pts.append((x1 + t * (x2 - x1), y1 + t * (y2 - y1)))
    return np.array(pts, dtype=float) if pts else np.empty((0, 2))


# ----------------------------------------------------------------------------
# PROCEDURAL SKYLINE
# ----------------------------------------------------------------------------
def _generate_skyline(pipeline_points):
    """
    Procedurally build a dense industrial block grid around Chakan.

    48 candidate plots are laid out on a jittered grid (fixed random seed, so
    the skyline never changes between reruns). Each gets a random footprint and
    a height of 30-150 m. The 30 plots FARTHEST from any pipeline are kept, so
    tall blocks never hide the data you are trying to show.
    """
    rng = random.Random(SKYLINE_SEED)
    pitch_x, pitch_y = SKYLINE_PITCH_M
    candidates = []

    for i in range(SKYLINE_COLS):
        for j in range(SKYLINE_ROWS):
            # grid position in metres from the camera centre, with jitter
            cx = (i - (SKYLINE_COLS - 1) / 2) * pitch_x + rng.uniform(-25, 25)
            cy = (j - (SKYLINE_ROWS - 1) / 2) * pitch_y + rng.uniform(-25, 25)
            half_w = rng.uniform(55, 75)    # footprint ~110-150 m
            half_d = rng.uniform(40, 60)    # footprint ~80-120 m
            height = rng.randint(*SKYLINE_HEIGHT_M)

            ring = [
                _offset_to_lonlat(CAMERA_LAT, CAMERA_LON, cx + sx * half_w, cy + sy * half_d)
                for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1))
            ]
            centre = _offset_to_lonlat(CAMERA_LAT, CAMERA_LON, cx, cy)
            candidates.append({"polygon": [list(p) for p in ring],
                               "height": height, "centre": centre})

    # Distance (metres) from each plot centre to the nearest pipeline sample
    if len(pipeline_points) > 0:
        cos_lat = math.cos(math.radians(CAMERA_LAT))
        for c in candidates:
            dx = (pipeline_points[:, 0] - c["centre"][0]) * _M_PER_DEG * cos_lat
            dy = (pipeline_points[:, 1] - c["centre"][1]) * _M_PER_DEG
            c["clearance"] = float(np.min(np.hypot(dx, dy)))
        candidates.sort(key=lambda c: c["clearance"], reverse=True)

    chosen = candidates[:SKYLINE_MAX_BUILDINGS]
    return [{"polygon": c["polygon"], "height": c["height"]} for c in chosen]


# ----------------------------------------------------------------------------
# ARCS, IOT NODES, LABELS
# ----------------------------------------------------------------------------
def _arc_records(anomalies, wind_from_deg):
    """Arcs from the worst anomalies to a point downwind (wind_from + 180)."""
    bearing = math.radians((wind_from_deg + 180.0) % 360.0)
    records = []
    for _, r in anomalies.iterrows():
        lat, lon = float(r["latitude"]), float(r["longitude"])
        ppm = float(r["methane_concentration_ppm"])
        length = ARC_MIN_LENGTH_M + ARC_LENGTH_PER_PPM_M * max(ppm - BACKGROUND_PPM, 0.0)
        t_lon, t_lat = _offset_to_lonlat(lat, lon, length * math.sin(bearing),
                                         length * math.cos(bearing))
        records.append({
            "source": [lon, lat],
            "target": [t_lon, t_lat],
            "width": min(2.0 + ppm / 2.0, 10.0),
            "tooltip_title": "PLUME VECTOR",
            "tooltip_body": (f"SOURCE: {ppm:.1f} PPM<br/>"
                             f"DRIFT: {length:.0f} M @ {math.degrees(bearing):.0f} DEG<br/>"
                             f"ORIGIN: {lat:.4f}, {lon:.4f}"),
        })
    return records


def _pipeline_intersections(features):
    """
    Find where different pipelines cross (exact segment-segment intersection,
    vectorised with numpy). Returns a list of (lon, lat).
    """
    segs, owner = [], []
    for idx, f in enumerate(features):
        c = f["geometry"]["coordinates"]
        for (x1, y1), (x2, y2) in zip(c[:-1], c[1:]):
            segs.append((x1, y1, x2, y2))
            owner.append(idx)
    n = len(segs)
    if n < 2 or n > MAX_SEGMENTS_FOR_INTERSECTION:
        return []

    seg = np.array(segs, dtype=float)
    own = np.array(owner)
    P = seg[:, :2]
    R = seg[:, 2:] - P

    with np.errstate(divide="ignore", invalid="ignore"):
        qp = P[None, :, :] - P[:, None, :]                       # q - p
        rxs = R[:, None, 0] * R[None, :, 1] - R[:, None, 1] * R[None, :, 0]
        t = (qp[..., 0] * R[None, :, 1] - qp[..., 1] * R[None, :, 0]) / rxs
        u = (qp[..., 0] * R[:, None, 1] - qp[..., 1] * R[:, None, 0]) / rxs

    hit = ((np.abs(rxs) > 1e-14) & (t >= 0) & (t <= 1) & (u >= 0) & (u <= 1)
           & (own[:, None] != own[None, :]))
    hit = np.triu(hit, 1)                                        # count each pair once

    ii, jj = np.nonzero(hit)
    pts = P[ii] + t[ii, jj][:, None] * R[ii]
    return [(float(x), float(y)) for x, y in pts]


def _iot_node_positions(features):
    """
    IoT sensor positions: real pipeline intersections when there are any;
    otherwise the end points of each pipeline (so the layer is never empty).
    Positions closer than ~1 m are merged; capped at MAX_IOT_NODES.
    """
    points = _pipeline_intersections(features)
    if not points:
        for f in features:
            c = f["geometry"]["coordinates"]
            points.extend([tuple(c[0]), tuple(c[-1])])

    unique = {}
    for lon, lat in points:
        unique.setdefault((round(lon, 5), round(lat, 5)), (lon, lat))
    return list(unique.values())[:MAX_IOT_NODES]


def _zone_status(flagged, lat, lon):
    """Data-driven zone status from anomalies within ZONE_RADIUS_M."""
    if len(flagged) == 0:
        return "NOMINAL"
    cos_lat = math.cos(math.radians(lat))
    dx = (flagged["longitude"].to_numpy() - lon) * _M_PER_DEG * cos_lat
    dy = (flagged["latitude"].to_numpy() - lat) * _M_PER_DEG
    near = np.hypot(dx, dy) <= ZONE_RADIUS_M
    if not near.any():
        return "NOMINAL"
    peak = float(flagged["methane_concentration_ppm"].to_numpy()[near].max())
    if peak >= ZONE_ALERT_PPM:
        return "ALERT"
    if peak >= ZONE_ELEVATED_PPM:
        return "ELEVATED"
    return "NOMINAL"


# ----------------------------------------------------------------------------
# MAIN FUNCTION
# ----------------------------------------------------------------------------
def render_pipeline_map(pipelines_gdf, observations_df, weather=None, lock_camera=False):
    """
    Build the cinematic 3D Chakan map and return it as a pydeck.Deck.

    pipelines_gdf   : LineString geometry (EPSG:4326); risk-engine columns
                      optional (used for colour + hover text).
    observations_df : latitude, longitude, methane_concentration_ppm
                      (+ is_ml_anomaly if available).
    weather         : optional dict from risk_engine.fetch_current_weather();
                      its wind_direction_deg (direction wind blows FROM) sets
                      the arc direction. Default: south-westerly (arcs go NE).
    """
    if "geometry" not in pipelines_gdf.columns:
        raise ValueError("pipelines_gdf needs a 'geometry' column")

    obs = _clean_observations(observations_df)
    flagged = _flagged(obs)
    wind_from = float(weather["wind_direction_deg"]) if weather else DEFAULT_WIND_FROM_DEG

    fc = _pipeline_features(pipelines_gdf)
    features = fc["features"]
    layers = []

    # --- 1. Laser geofence -------------------------------------------------------
    layers.append(pdk.Layer(
        "PolygonLayer",
        data=[{"polygon": _geofence_ring()}],
        get_polygon="polygon",
        get_fill_color=[5, 5, 15, 200],        # blacks out the ground
        get_line_color=CYAN + [255],
        get_line_width=4,
        line_width_units="pixels",             # never metres -> no explosion
        stroked=True,
        filled=True,
        extruded=False,
        pickable=False,
    ))

    # --- 2. Toxic ground-glow ------------------------------------------------------
    if len(obs) > 0:
        heat_data = [{"position": [float(r.longitude), float(r.latitude)],
                      "weight": max(float(r.methane_concentration_ppm) - BACKGROUND_PPM, 0.0)}
                     for r in obs.itertuples()]
        layers.append(pdk.Layer(
            "HeatmapLayer",
            data=heat_data,
            get_position="position",
            get_weight="weight",
            radius_pixels=HEATMAP_RADIUS_PX,
            intensity=2.5,
            threshold=0.03,
            color_range=HEATMAP_COLOR_RANGE,
            aggregation="SUM",
            opacity=0.9,
            pickable=False,
        ))

    # --- 3. Procedural 3D skyline --------------------------------------------------
    layers.append(pdk.Layer(
        "PolygonLayer",
        data=_generate_skyline(_sample_points(features)),
        get_polygon="polygon",
        get_elevation="height",
        get_fill_color=[8, 8, 12, 255],         # matte black
        get_line_color=CYAN + [70],             # faint cyan wireframe
        get_line_width=1,
        line_width_units="pixels",
        extruded=True,
        wireframe=True,
        filled=True,
        stroked=False,
        material=MATERIAL,
        pickable=False,
    ))

    # --- 4 + 5. Neon-bloom pipelines (two overlapping GeoJsonLayers) -----------------
    if features:
        layers.append(pdk.Layer(              # bloom: wide + translucent
            "GeoJsonLayer",
            data=fc,
            get_line_color="properties.bloom_color",
            get_line_width=16,
            line_width_units="pixels",
            line_cap_rounded=True,
            line_joint_rounded=True,
            filled=False,
            pickable=False,
        ))
        layers.append(pdk.Layer(              # core: thin + solid
            "GeoJsonLayer",
            data=fc,
            get_line_color="properties.core_color",
            get_line_width=3,
            line_width_units="pixels",
            line_cap_rounded=True,
            line_joint_rounded=True,
            filled=False,
            pickable=True,
            auto_highlight=True,
        ))

    # --- 6. Extruded hex-matrix -------------------------------------------------------
    if len(obs) > 0:
        hex_data = [{"position": [float(r.longitude), float(r.latitude)],
                     "ppm": float(r.methane_concentration_ppm)}
                    for r in obs.itertuples()]
        layers.append(pdk.Layer(
            "HexagonLayer",
            data=hex_data,
            get_position="position",
            get_color_weight="ppm",
            get_elevation_weight="ppm",
            color_aggregation="MAX",            # one hotspot lights its whole hexagon
            elevation_aggregation="MAX",
            color_domain=[BACKGROUND_PPM, SATURATION_PPM],
            elevation_domain=[BACKGROUND_PPM, SATURATION_PPM],
            color_range=HEX_COLOR_RANGE,
            elevation_range=HEX_HEIGHT_RANGE_M,
            radius=HEX_RADIUS_M,
            coverage=0.9,
            extruded=True,
            opacity=0.9,
            material=MATERIAL,
            pickable=False,
        ))

    # --- 7. Trajectory arcs ------------------------------------------------------------
    top = flagged.nlargest(ARC_COUNT, "methane_concentration_ppm")
    arcs = _arc_records(top, wind_from) if len(top) > 0 else []
    if arcs:
        layers.append(pdk.Layer(
            "ArcLayer",
            data=arcs,
            get_source_position="source",
            get_target_position="target",
            get_width="width",
            width_units="pixels",
            width_min_pixels=2,
            get_height=ARC_HEIGHT_FACTOR,       # climbs into the sky
            get_source_color=GOLD + [240],
            get_target_color=CRIMSON + [50],
            pickable=True,
        ))

    # --- 8. IoT sensor nodes (halo + core) ---------------------------------------------
    nodes = []
    for k, (lon, lat) in enumerate(_iot_node_positions(features), start=1):
        nodes.append({
            "position": [lon, lat],
            "tooltip_title": f"IOT NODE {k:02d}",
            "tooltip_body": f"POSITION: {lat:.4f}, {lon:.4f}<br/>TYPE: PIPELINE JUNCTION SENSOR",
        })
    if nodes:
        layers.append(pdk.Layer(              # large, transparent halo
            "ScatterplotLayer",
            data=nodes,
            get_position="position",
            get_radius=22,
            radius_units="pixels",
            get_fill_color=CYAN + [45],
            stroked=False,
            pickable=False,
        ))
        layers.append(pdk.Layer(              # small, solid core
            "ScatterplotLayer",
            data=nodes,
            get_position="position",
            get_radius=6,
            radius_units="pixels",
            get_fill_color=[255, 255, 255, 255],
            stroked=True,
            get_line_color=CYAN + [255],
            get_line_width=2,
            line_width_units="pixels",
            pickable=True,
        ))

    # --- 9. SCADA labels --------------------------------------------------------------
    labels = []
    for name, lat, lon in SCADA_ZONES:
        status = _zone_status(flagged, lat, lon)
        labels.append({
            "text": f"[SYS.OP: {name} // STATUS: {status}]",
            "position": [lon, lat, LABEL_ALTITUDE_M],
            "color": (CRIMSON if status == "ALERT" else GOLD if status == "ELEVATED"
                      else CYAN) + [255],
        })
    layers.append(pdk.Layer(
        "TextLayer",
        data=labels,
        get_text="text",
        get_position="position",
        get_color="color",
        get_size=13,
        size_units="pixels",
        get_text_anchor='"middle"',
        get_alignment_baseline='"center"',
        billboard=True,
        font_family="Courier New, monospace",
        font_weight=700,
        pickable=False,
    ))

    # --- Camera -------------------------------------------------------------------------
    view_state = pdk.ViewState(
        latitude=CAMERA_LAT,
        longitude=CAMERA_LON,
        zoom=CAMERA_ZOOM,
        min_zoom=MIN_ZOOM,
        max_zoom=MAX_ZOOM,
        pitch=CAMERA_PITCH,
        min_pitch=MIN_PITCH,
        max_pitch=MAX_PITCH,
        bearing=CAMERA_BEARING,
    )
    # Scroll-zoom only (inside the min/max band); no pan, rotate or keyboard.
    view = pdk.View(type="MapView", controller={
        "scrollZoom": True,
        "dragPan": False,
        "dragRotate": False,
        "touchRotate": False,
        "doubleClickZoom": False,
        "keyboard": False,
    })

    return pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        views=[view],
        map_style="dark",
        tooltip=TOOLTIP,
    )