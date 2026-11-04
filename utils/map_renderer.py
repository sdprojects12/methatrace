"""
map_renderer.py  --  MethaTrace live asset map (pydeck / deck.gl)

    from utils.map_renderer import render_pipeline_map, get_map_conditions_html

    deck = render_pipeline_map(pipelines_gdf, observations_df)
    st.pydeck_chart(deck, width="stretch", height=680)

    st.markdown(
        get_map_conditions_html(weather, observations_df, pipelines_gdf),
        unsafe_allow_html=True,
    )

`render_pipeline_map()` returns a pydeck.Deck. It never draws anything itself.

Visual language
--------------
The map is intentionally calm: a label-free dark basemap, a fine geofence,
soft hotspot ground glows, glowing risk-coloured pipeline cores and small
extruded asset compounds. Only genuine hotspots get vertical columns, so the
eye is drawn to the signal instead of the decoration.

Data safety rails
-----------------
* Every observation / pipeline vertex must lie inside the Chakan bounding box
  (lat 18.70-18.85, lon 73.70-73.90) or it is dropped.
* The camera starts from one hard-coded ViewState and is then fully unlocked
  (drag = pan, scroll = zoom, right-drag / ctrl-drag = orbit and tilt).
* Every line width is in pixels; every radius is in metres; every height is
  clamped. No layer depends on raw data magnitude for its size.

Honesty notes
-------------
* Factory compounds are STYLISED monoliths at APPROXIMATE positions. They are
  not surveyed footprints. See FACTORY_SITES below.
* Risk colours come from the SIMULATED risk score of risk_engine.py.
"""

import html
import logging
import math
import random
from datetime import datetime

import numpy as np
import pandas as pd
import pydeck as pdk

try:  # keep the condition card's thresholds in sync with the risk engine
    from utils.risk_engine import HIGH_THRESHOLD, MEDIUM_THRESHOLD
except ImportError:  # standalone use
    HIGH_THRESHOLD, MEDIUM_THRESHOLD = 60, 30

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# SPATIAL BOUNDING BOX (anti-global filter)
# ----------------------------------------------------------------------------
BBOX_LAT_MIN, BBOX_LAT_MAX = 18.70, 18.85
BBOX_LON_MIN, BBOX_LON_MAX = 73.70, 73.90

# ----------------------------------------------------------------------------
# CAMERA: cinematic start, controls fully unlocked
# ----------------------------------------------------------------------------
VIEW_LAT, VIEW_LON = 18.7505, 73.8040
VIEW_ZOOM = 12.25
VIEW_PITCH = 30.0
VIEW_BEARING = 70.0

# ----------------------------------------------------------------------------
# PALETTE (one source of truth)
# ----------------------------------------------------------------------------
COLOR_CRITICAL = [255, 96, 116]     # refined coral
COLOR_WARNING = [255, 177, 71]      # warm amber
COLOR_SAFE = [56, 206, 193]         # muted teal
COLOR_UNRATED = [132, 152, 172]     # slate

RISK_STYLE = {   # risk_level from risk_engine -> (label, colour)
    "High": ("CRITICAL", COLOR_CRITICAL),
    "Medium": ("WARNING", COLOR_WARNING),
    "Low": ("SAFE", COLOR_SAFE),
}
STATUS_TO_RISK = {"Leaking": "High", "Maintenance": "Medium", "Active": "Low"}

# ----------------------------------------------------------------------------
# GEOFENCE
# ----------------------------------------------------------------------------
GEOFENCE_LAT_MIN, GEOFENCE_LAT_MAX = 18.73, 18.80
GEOFENCE_LON_MIN, GEOFENCE_LON_MAX = 73.78, 73.85

# ----------------------------------------------------------------------------
# METHANE
# ----------------------------------------------------------------------------
BACKGROUND_PPM = 2.0          # ~ normal atmosphere
HOTSPOT_PPM = 4.0             # at/above this a reading becomes a column
SATURATION_PPM = 8.0          # column reaches full height / full coral here
MAX_PILLARS = 80

PILLAR_RADIUS_M = 48
PILLAR_HEIGHT_RANGE_M = [180, 900]      # hotspot threshold -> saturation
DANGER_RING_RADIUS_M = 150
DANGER_GLOW_RADIUS_M = 360
PILLAR_MATERIAL = {"ambient": 1.0, "diffuse": 0.0, "shininess": 0,
                   "specularColor": [0, 0, 0]}

# ----------------------------------------------------------------------------
# FACTORIES (stylised monoliths at APPROXIMATE positions)
# ----------------------------------------------------------------------------
# !! SCHEMATIC, NOT SURVEYED !!  Positions are placed near the camera centre;
# replace with surveyed coordinates before presenting them as real.
# (name, lat, lon)
FACTORY_SITES = [
    ("Tata Motors",    18.7700, 73.8050),
    ("Mahindra",       18.7550, 73.8250),
    ("Bajaj Corridor", 18.7650, 73.8200),
]
# Each compound: (dx_m, dy_m, width_m, depth_m, height_m, role) from site centre
COMPOUND_BLUEPRINT = [
    (0,    0,   235, 125, 62,  "hall"),     # main assembly hall
    (-168, 24,  108, 88,  42,  "hall"),     # annex
    (148,  -66, 98,  78,  48,  "hall"),     # paint shop
    (-40,  112, 56,  56,  205, "tower"),    # the monolith
    (92,   104, 26,  26,  158, "tower"),    # stack
    (122,  104, 26,  26,  138, "tower"),    # stack
]
SITE_CLEARANCE_M = 200      # keep compounds this far from pipelines if possible
SITE_NUDGE_STEP_M = 350
LABEL_CLEARANCE_M = 55      # label floats this far above the tallest block
LABEL_PIXEL_OFFSET = {      # nudge chips apart at the default camera angle
    "Tata Motors": [46, -2],
    "Bajaj Corridor": [-10, -5],
    "Mahindra": [18, 6],
}

HALL_FILL = [24, 36, 55, 255]
TOWER_FILL = [31, 50, 74, 255]
EDGE_COLOR = [126, 194, 220, 148]

# Shared polished-metal material for extruded structures
MATERIAL = {
    "ambient": 0.42,
    "diffuse": 0.52,
    "shininess": 72,
    "specularColor": [132, 190, 220],
}

_M_PER_DEG = 111_320.0

# ----------------------------------------------------------------------------
# TOOLTIP: quiet, precise, readable
# ----------------------------------------------------------------------------
TOOLTIP = {
    "html": "{tooltip_html}",
    "style": {
        "backgroundColor": "rgba(7, 12, 20, 0.96)",
        "border": "1px solid rgba(126, 160, 190, 0.32)",
        "borderRadius": "10px",
        "boxShadow": "0 18px 46px rgba(0, 0, 0, 0.5)",
        "color": "#dfeaf5",
        "fontFamily": "'Inter', 'Segoe UI', sans-serif",
        "fontSize": "12px",
        "padding": "0",
        "maxWidth": "340px",
    },
}

# Import-time sanity checks
assert BBOX_LAT_MIN <= VIEW_LAT <= BBOX_LAT_MAX and BBOX_LON_MIN <= VIEW_LON <= BBOX_LON_MAX
assert BBOX_LAT_MIN <= GEOFENCE_LAT_MIN and GEOFENCE_LAT_MAX <= BBOX_LAT_MAX
assert BBOX_LON_MIN <= GEOFENCE_LON_MIN and GEOFENCE_LON_MAX <= BBOX_LON_MAX


# ----------------------------------------------------------------------------
# SMALL HELPERS
# ----------------------------------------------------------------------------
def _esc(value, default="N/A"):
    """HTML-escaped text, or `default` if the value is missing."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return default
    return html.escape(str(value))


def _rgb(color, alpha=None):
    return list(color) + ([alpha] if alpha is not None else [])


def _css(color, alpha=1.0):
    return f"rgba({color[0]},{color[1]},{color[2]},{alpha})"


def _offset_to_lonlat(lat0, lon0, dx_m, dy_m):
    """Move dx metres east / dy metres north from (lat0, lon0)."""
    lat = lat0 + dy_m / _M_PER_DEG
    lon = lon0 + dx_m / (_M_PER_DEG * math.cos(math.radians(lat0)))
    return lon, lat


def _in_bbox(lat, lon):
    return (np.isfinite(lat) and np.isfinite(lon)
            and BBOX_LAT_MIN <= lat <= BBOX_LAT_MAX
            and BBOX_LON_MIN <= lon <= BBOX_LON_MAX)


def _lerp_color(c1, c2, t):
    t = min(max(t, 0.0), 1.0)
    return [int(round(a + (b - a) * t)) for a, b in zip(c1, c2)]


def _number(value, default=None):
    """Coerce a value to float, returning `default` when it is unusable."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number if math.isfinite(number) else default


def compass_label(degrees):
    """Meteorological degrees -> 16-point compass label."""
    if degrees is None:
        return "N/A"
    points = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
              "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return points[int((degrees % 360) / 22.5 + 0.5) % 16]


def _tooltip_html(title, rows, accent=COLOR_SAFE):
    """HUD tooltip: quiet title bar + label/value rows (values pre-escaped)."""
    head = (
        f'<div style="padding:9px 13px;letter-spacing:0.14em;font-size:10px;'
        f'font-weight:700;text-transform:uppercase;color:{_css(accent)};'
        f'border-bottom:1px solid {_css(accent, 0.28)};'
        f'background:linear-gradient(90deg,{_css(accent, 0.14)},transparent);">'
        f'{title}</div>'
    )
    body = "".join(
        f'<div style="display:flex;justify-content:space-between;gap:18px;'
        f'padding:3px 13px;"><span style="color:#7d95aa;">{label}</span>'
        f'<span style="text-align:right;color:#dce8f4;">{value}</span></div>'
        for label, value in rows
    )
    return f'{head}<div style="padding:7px 0 9px 0;">{body}</div>'


# ----------------------------------------------------------------------------
# INPUT SANITISING
# ----------------------------------------------------------------------------
def _sanitize_observations(observations_df):
    """Numeric lat/lon/ppm rows inside the Chakan bounding box only."""
    needed = ["latitude", "longitude", "methane_concentration_ppm"]
    missing = set(needed) - set(observations_df.columns)
    if missing:
        raise ValueError(f"observations_df is missing columns: {sorted(missing)}")

    df = observations_df.copy()
    for col in needed:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=needed)
    inside = (df["latitude"].between(BBOX_LAT_MIN, BBOX_LAT_MAX)
              & df["longitude"].between(BBOX_LON_MIN, BBOX_LON_MAX))
    dropped = len(observations_df) - int(inside.sum())
    if dropped:
        logger.warning("Dropped %d observation(s) outside the Chakan bounding box "
                       "or with invalid values.", dropped)
    return df[inside]


def _geometry_to_paths(geometry):
    """LineString / MultiLineString -> list of [[lon, lat], ...]."""
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


def _risk_level(row):
    level = row.get("risk_level")
    if isinstance(level, str) and level in RISK_STYLE:
        return level
    return STATUS_TO_RISK.get(row.get("status"))


def _sanitize_pipelines(pipelines_gdf):
    """
    GeoJSON FeatureCollection of pipeline paths that lie ENTIRELY inside the
    bounding box. Colours and tooltip HTML live in `properties` and also at the
    top level of each feature (so hover works however pydeck resolves fields).
    Coordinates carry a small z so lines never z-fight with the ground polygon.
    """
    if "geometry" not in pipelines_gdf.columns:
        raise ValueError("pipelines_gdf needs a 'geometry' column")

    features, nodes, dropped = [], {}, 0
    for _, row in pipelines_gdf.iterrows():
        level = _risk_level(row)
        label, color = RISK_STYLE.get(level, ("UNRATED", COLOR_UNRATED))

        score = row.get("simulated_risk_score")
        score_txt = "N/A" if score is None or pd.isna(score) else f"{float(score):.0f}/100"
        tip = _tooltip_html(
            f"Pipeline // {_esc(row.get('pipeline_id'), 'UNKNOWN')}",
            [
                ("Risk", f'<b style="color:{_css(color)};">{label}</b>'),
                ("Simulated score", score_txt),
                ("Type", _esc(row.get("type"))),
                ("Status", _esc(row.get("status"))),
                ("Analysis", _esc(row.get("risk_explanation"), "No risk analysis available.")),
            ],
            accent=color,
        )
        for path in _geometry_to_paths(row["geometry"]):
            if not all(_in_bbox(lat, lon) for lon, lat in path):
                dropped += 1
                continue
            features.append({
                "type": "Feature",
                "geometry": {"type": "LineString",
                             "coordinates": [[lon, lat, 4.0] for lon, lat in path]},
                "properties": {
                    "core": _rgb(color, 255),
                    "glow": _rgb(color, 30),
                    "mid": _rgb(color, 92),
                    "tooltip_html": tip,
                },
                "tooltip_html": tip,
            })
            for lon, lat in (path[0], path[-1]):
                nodes[(round(lon, 6), round(lat, 6))] = _rgb(color, 255)

    if dropped:
        logger.warning("Dropped %d pipeline path(s) with vertices outside the "
                       "Chakan bounding box.", dropped)

    node_records = [{"position": [lon, lat], "color": color}
                    for (lon, lat), color in nodes.items()]
    return {"type": "FeatureCollection", "features": features}, node_records


def _pipeline_sample_points(features, step_deg=0.00025):
    """Densify pipeline paths (~25 m) into an (N, 2) lon/lat array."""
    pts = []
    for f in features:
        c = f["geometry"]["coordinates"]
        for (x1, y1, _), (x2, y2, _) in zip(c[:-1], c[1:]):
            n = max(int(math.hypot(x2 - x1, y2 - y1) / step_deg), 1)
            pts.extend((x1 + k / n * (x2 - x1), y1 + k / n * (y2 - y1)) for k in range(n + 1))
    return np.array(pts, dtype=float) if pts else np.empty((0, 2))


# ----------------------------------------------------------------------------
# FACTORIES
# ----------------------------------------------------------------------------
def _clearance_m(lon, lat, samples):
    """Distance in metres from a point to the nearest pipeline sample."""
    if len(samples) == 0:
        return float("inf")
    dx = (samples[:, 0] - lon) * _M_PER_DEG * math.cos(math.radians(lat))
    dy = (samples[:, 1] - lat) * _M_PER_DEG
    return float(np.min(np.hypot(dx, dy)))


def _place_site(lat, lon, samples):
    """
    Keep the compound where requested unless a pipeline runs through it; then
    try nudging it up to 2 steps in 8 directions and take the first spot with
    enough clearance (else the best one found). Result stays inside the bbox.
    """
    candidates = [(0.0, 0.0)]
    for ring in (1, 2):
        for k in range(8):
            ang = math.radians(45 * k)
            candidates.append((ring * SITE_NUDGE_STEP_M * math.sin(ang),
                               ring * SITE_NUDGE_STEP_M * math.cos(ang)))
    best, best_clear = (lon, lat), -1.0
    for dx, dy in candidates:
        c_lon, c_lat = _offset_to_lonlat(lat, lon, dx, dy)
        if not _in_bbox(c_lat, c_lon):
            continue
        clear = _clearance_m(c_lon, c_lat, samples)
        if clear >= SITE_CLEARANCE_M:
            return c_lon, c_lat
        if clear > best_clear:
            best, best_clear = (c_lon, c_lat), clear
    return best


def _build_factories(samples):
    """Return (building_records, label_records) for all factory compounds."""
    buildings, labels = [], []
    for name, lat, lon in FACTORY_SITES:
        if not _in_bbox(lat, lon):
            continue
        c_lon, c_lat = _place_site(lat, lon, samples)
        rng = random.Random(name)           # same look on every rerun
        tallest = 0.0

        for dx, dy, w, d, h, role in COMPOUND_BLUEPRINT:
            h = h * rng.uniform(0.92, 1.12)
            tallest = max(tallest, h)
            ring = [list(_offset_to_lonlat(c_lat, c_lon, dx + sx * w / 2, dy + sy * d / 2))
                    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1), (-1, -1))]
            tip = _tooltip_html(
                f"Asset // {html.escape(name)}",
                [("Class", "Industrial facility"),
                 ("Structure", role.title()),
                 ("Height", f"{h:.0f} m (stylised)"),
                 ("Position", "Schematic / approximate")],
            )
            buildings.append({
                "polygon": ring,
                "height": round(h, 1),
                "fill": TOWER_FILL if role == "tower" else HALL_FILL,
                "tooltip_html": tip,
            })

        labels.append({"text": name,
                       "position": [c_lon, c_lat, tallest + LABEL_CLEARANCE_M],
                       "pixel_offset": LABEL_PIXEL_OFFSET.get(name, [0, 0])})
    return buildings, labels


# ----------------------------------------------------------------------------
# METHANE
# ----------------------------------------------------------------------------
def _pillar_records(hot):
    """One column + ground glow per strong reading (height is clamped)."""
    records = []
    for r in hot.nlargest(MAX_PILLARS, "methane_concentration_ppm").itertuples():
        ppm = float(r.methane_concentration_ppm)
        frac = min(max((ppm - HOTSPOT_PPM) / (SATURATION_PPM - HOTSPOT_PPM), 0.0), 1.0)
        lo, hi = PILLAR_HEIGHT_RANGE_M
        color = _lerp_color(COLOR_WARNING, COLOR_CRITICAL, frac)
        lon, lat = float(r.longitude), float(r.latitude)
        records.append({
            "position": [lon, lat],
            "height": lo + frac * (hi - lo),     # never exceeds hi, whatever the PPM
            "core": _rgb(color, 242),
            "ring_fill": _rgb(color, 9),
            "ring_line": _rgb(color, 176),
            "glow": _rgb(color, 16),
            "label": f"{ppm:.1f} ppm",
            "label_position": [lon, lat, lo + frac * (hi - lo) + 42],
            "tooltip_html": _tooltip_html(
                "Methane // Hotspot",
                [("Concentration", f'<b style="color:{_css(color)};">{ppm:.1f} ppm</b>'),
                 ("Above baseline", f"+{max(ppm - BACKGROUND_PPM, 0):.1f} ppm"),
                 ("Position", f"{lat:.4f}, {lon:.4f}")],
                accent=color),
        })
    return records


# ----------------------------------------------------------------------------
# MAIN FUNCTION
# ----------------------------------------------------------------------------
def render_pipeline_map(pipelines_gdf, observations_df, weather=None):
    """
    Build the Chakan live asset map and return it as a pydeck.Deck.

    pipelines_gdf   : LineString `geometry` (EPSG:4326); optional pipeline_id,
                      type, status and the risk-engine columns risk_level,
                      simulated_risk_score, risk_explanation.
    observations_df : latitude, longitude, methane_concentration_ppm.
    weather         : accepted so existing calls keep working; it is displayed
                      in the separate conditions card, not drawn on the map.
    """
    obs = _sanitize_observations(observations_df)
    pipeline_fc, node_records = _sanitize_pipelines(pipelines_gdf)
    features = pipeline_fc["features"]
    samples = _pipeline_sample_points(features)

    hot = obs[obs["methane_concentration_ppm"] >= HOTSPOT_PPM]
    pillars = _pillar_records(hot) if len(hot) else []
    peak_label = []
    if pillars:
        peak = max(pillars, key=lambda p: p["height"])
        peak_label = [{"text": f"Peak {peak['label']}",
                       "position": peak["label_position"]}]
    buildings, labels = _build_factories(samples)

    layers = []

    # 1. Geofence: barely-there ground tint + a single hairline boundary.
    layers.append(pdk.Layer(
        "PolygonLayer",
        data=[{"polygon": [
            [GEOFENCE_LON_MIN, GEOFENCE_LAT_MIN], [GEOFENCE_LON_MAX, GEOFENCE_LAT_MIN],
            [GEOFENCE_LON_MAX, GEOFENCE_LAT_MAX], [GEOFENCE_LON_MIN, GEOFENCE_LAT_MAX],
            [GEOFENCE_LON_MIN, GEOFENCE_LAT_MIN]]}],
        get_polygon="polygon",
        get_fill_color=[18, 42, 58, 22],
        get_line_color=[72, 176, 184, 116],
        get_line_width=1,
        line_width_units="'pixels'",
        stroked=True, filled=True, extruded=False, pickable=False,
    ))

    # 2. Sensor constellation: tiny dots that show monitoring coverage.
    if len(obs) > 0:
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=[{"position": [float(r.longitude), float(r.latitude)]}
                  for r in obs.itertuples()],
            get_position="position",
            get_radius=1.4,
            radius_units="'pixels'",
            radius_min_pixels=1,
            get_fill_color=[120, 204, 216, 38],
            stroked=False, filled=True, pickable=False,
        ))

    # 4. Hotspot ground treatment: wide aura, then a precise survey ring.
    if pillars:
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=pillars,
            get_position="position",
            get_radius=DANGER_GLOW_RADIUS_M,
            radius_units="'meters'",
            get_fill_color="glow",
            stroked=False, filled=True, pickable=False,
        ))
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=pillars,
            get_position="position",
            get_radius=DANGER_RING_RADIUS_M,
            radius_units="'meters'",
            get_fill_color="ring_fill",
            get_line_color="ring_line",
            get_line_width=1.2,
            line_width_units="'pixels'",
            stroked=True, filled=True, pickable=False,
        ))

    # 5. Pipelines: dark casing -> soft bloom -> crisp risk-coloured core.
    if features:
        layers.append(pdk.Layer(
            "GeoJsonLayer", data=pipeline_fc,
            get_line_color=[2, 6, 12, 235],
            get_line_width=5.5, line_width_units="'pixels'", line_width_min_pixels=5,
            line_cap_rounded=True, line_joint_rounded=True,
            filled=False, pickable=False,
        ))
        layers.append(pdk.Layer(
            "GeoJsonLayer", data=pipeline_fc,
            get_line_color="properties.glow",
            get_line_width=12, line_width_units="'pixels'",
            line_cap_rounded=True, line_joint_rounded=True,
            filled=False, pickable=False,
        ))
        layers.append(pdk.Layer(
            "GeoJsonLayer", data=pipeline_fc,
            get_line_color="properties.core",
            get_line_width=1.6, line_width_units="'pixels'", line_width_min_pixels=1.5,
            line_cap_rounded=True, line_joint_rounded=True,
            filled=False, pickable=True,
            auto_highlight=True, highlight_color=[255, 255, 255, 55],
        ))

    # 6. Small junction nodes: polished detail, not decoration.
    if node_records:
        layers.append(pdk.Layer(
            "ScatterplotLayer",
            data=node_records,
            get_position="position",
            get_radius=4,
            radius_units="'pixels'",
            get_fill_color=[5, 11, 19, 255],
            get_line_color="color",
            get_line_width=1.2,
            line_width_units="'pixels'",
            stroked=True, filled=True, pickable=False,
        ))

    # 7. Factory monoliths: low, dark and architectural.
    if buildings:
        layers.append(pdk.Layer(
            "PolygonLayer",
            data=buildings,
            get_polygon="polygon",
            get_elevation="height",
            get_fill_color="fill",
            get_line_color=EDGE_COLOR,
            get_line_width=1, line_width_units="'pixels'",
            extruded=True, wireframe=True, filled=True, stroked=False,
            material=MATERIAL,
            pickable=True,
            auto_highlight=True, highlight_color=[94, 196, 210, 48],
        ))

    # 8. Methane columns: flat-lit coral data bars, labelled with PPM.
    if pillars:
        layers.append(pdk.Layer(
            "ColumnLayer",
            data=pillars,
            get_position="position",
            get_elevation="height",
            elevation_scale=1,
            radius=PILLAR_RADIUS_M,
            disk_resolution=24,
            extruded=True,
            get_fill_color="core",
            material=PILLAR_MATERIAL,
            pickable=True,
            auto_highlight=True, highlight_color=[255, 255, 255, 80],
        ))
        layers.append(pdk.Layer(
            "TextLayer",
            data=peak_label,
            get_text="text",
            get_position="position",
            get_color=[255, 226, 210, 244],
            get_size=10,
            size_units="'pixels'",
            billboard=True,
            font_family="'Inter, Segoe UI, sans-serif'",
            font_weight=600,
            background=True,
            get_background_color=[26, 11, 13, 228],
            background_padding=[6, 3],
            pickable=False,
        ))

    # 9. Asset labels: small, calm chips floating above each compound.
    if labels:
        layers.append(pdk.Layer(
            "TextLayer",
            data=labels,
            get_text="text",
            get_position="position",
            get_pixel_offset="pixel_offset",
            get_color=[222, 235, 245, 238],
            get_size=12,
            size_units="'pixels'",
            billboard=True,
            font_family="'Inter, Segoe UI, sans-serif'",
            font_weight=600,
            background=True,
            get_background_color=[7, 13, 22, 214],
            background_padding=[8, 4],
            pickable=False,
        ))

    # Camera: cinematic start; default controller = fully unlocked
    # (drag = pan, scroll = zoom, right-drag / ctrl-drag = orbit and tilt)
    view_state = pdk.ViewState(
        latitude=VIEW_LAT, longitude=VIEW_LON,
        zoom=VIEW_ZOOM, pitch=VIEW_PITCH, bearing=VIEW_BEARING,
        min_zoom=11, max_zoom=18,
    )
    return pdk.Deck(
        layers=layers,
        initial_view_state=view_state,
        map_style="dark_no_labels",
        map_provider="carto",
        tooltip=TOOLTIP,
    )


# ----------------------------------------------------------------------------
# MAP CONDITIONS CARD (small, professional replacement for the old legend)
# ----------------------------------------------------------------------------
_CONDITIONS_CSS = """
<style>
.mt-conditions{
  width:332px;padding:15px 17px 12px;border-radius:15px;
  border:1px solid rgba(138,170,198,.20);
  background:linear-gradient(165deg,rgba(14,23,36,.91),rgba(6,11,19,.94));
  box-shadow:0 22px 55px rgba(0,0,0,.52),inset 0 1px 0 rgba(255,255,255,.035);
  backdrop-filter:blur(16px) saturate(135%);
  -webkit-backdrop-filter:blur(16px) saturate(135%);
  color:#e7eff8;font-family:'Inter','Segoe UI',sans-serif;
  pointer-events:none;user-select:none;
}
.mt-conditions *{box-sizing:border-box}
.mt-conditions__head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:13px}
.mt-conditions__title{display:flex;align-items:center;gap:8px;font-size:9.5px;font-weight:700;letter-spacing:.17em;color:#9ab0c4;text-transform:uppercase}
.mt-conditions__dot{width:6px;height:6px;border-radius:50%;background:#48d6b3;box-shadow:0 0 0 4px rgba(72,214,179,.13)}
.mt-conditions__dot.alert{background:#ffb147;box-shadow:0 0 0 4px rgba(255,177,71,.14)}
.mt-conditions__badge{font-size:8.5px;font-weight:700;letter-spacing:.15em;color:#7fe3c9;padding:4px 7px;border-radius:999px;border:1px solid rgba(72,214,179,.24);background:rgba(72,214,179,.08);text-transform:uppercase}
.mt-conditions__badge.alert{color:#ffc173;border-color:rgba(255,177,71,.28);background:rgba(255,177,71,.09)}
.mt-conditions__wind{display:flex;align-items:center;gap:12px;padding:0 0 12px;border-bottom:1px solid rgba(138,170,198,.12)}
.mt-wind-icon{width:46px;height:46px;flex:0 0 46px;display:grid;place-items:center;border-radius:50%;border:1px solid rgba(138,170,198,.18);background:radial-gradient(circle at 50% 45%,rgba(72,160,174,.16),transparent 68%)}
.mt-conditions__label{font-size:8.5px;font-weight:700;letter-spacing:.16em;color:#7f97ac;text-transform:uppercase;line-height:1.2}
.mt-conditions__value{font-size:20px;font-weight:600;letter-spacing:-.02em;line-height:1.2;color:#f1f7fc}
.mt-conditions__value small{font-size:10px;font-weight:500;letter-spacing:.01em;color:#8fa6b9;margin-left:3px}
.mt-conditions__sub{font-size:10px;color:#7f97ac;line-height:1.3;margin-top:1px}
.mt-conditions__grid{display:grid;grid-template-columns:repeat(3,1fr);gap:0;padding:11px 0 10px}
.mt-conditions__cell{padding:0 10px;border-left:1px solid rgba(138,170,198,.10)}
.mt-conditions__cell:first-child{padding-left:0;border-left:0}
.mt-conditions__cell .mt-conditions__value{font-size:16px;margin-top:1px}
.mt-conditions__cell .mt-conditions__value small{font-size:9px}
.mt-conditions__foot{display:flex;align-items:center;justify-content:space-between;gap:10px;padding-top:9px;border-top:1px solid rgba(138,170,198,.12);font-size:8.5px;font-weight:600;letter-spacing:.12em;color:#627b90;text-transform:uppercase}
@media (max-width:760px){.mt-conditions{width:280px;padding:12px 13px 10px}.mt-conditions__grid{grid-template-columns:repeat(2,1fr);row-gap:9px}.mt-conditions__cell:nth-child(3){display:none}}
</style>
"""


def get_map_conditions_html(weather=None, observations_df=None,
                            pipelines_gdf=None, alert=False):
    """
    Compact glass card that describes the map's live conditions: wind, ambient
    temperature, peak methane and flagged readings. This deliberately replaces
    the old full colour legend.

    The caller positions the returned block over the map (see app.py). It has
    no interactive elements, so pointer events pass through to deck.gl.
    """
    weather = weather or {}
    wind_speed = _number(weather.get("wind_speed_kmh"))
    wind_from = _number(weather.get("wind_direction_deg"))
    temperature = _number(weather.get("temperature_c"))

    peak_ppm = None
    hotspot_count = 0
    if observations_df is not None and "methane_concentration_ppm" in observations_df.columns:
        ppm = pd.to_numeric(observations_df["methane_concentration_ppm"], errors="coerce").dropna()
        if len(ppm):
            peak_ppm = float(ppm.max())
            hotspot_count = int((ppm >= HOTSPOT_PPM).sum())

    asset_count = 0
    if pipelines_gdf is not None:
        try:
            asset_count = int(len(pipelines_gdf))
        except TypeError:
            asset_count = 0

    weather_offline = weather.get("source") == "fallback_mock"
    if alert:
        badge, badge_class, dot_class = "Simulation", " alert", " alert"
    elif weather_offline:
        badge, badge_class, dot_class = "Met offline", " alert", " alert"
    else:
        badge, badge_class, dot_class = "Live", "", ""

    if wind_from is None:
        arrow_rotation = 0
        wind_from_text = "Direction unavailable"
    else:
        arrow_rotation = (wind_from + 180.0) % 360.0   # arrow points downwind
        wind_from_text = f"from {compass_label(wind_from)} &middot; {wind_from:.0f}&deg;"

    wind_value = "N/A" if wind_speed is None else f"{wind_speed:.1f}"
    temp_value = "N/A" if temperature is None else f"{temperature:.1f}"
    peak_value = "N/A" if peak_ppm is None else f"{peak_ppm:.1f}"
    excess_value = "" if peak_ppm is None else f"+{max(peak_ppm - BACKGROUND_PPM, 0):.1f} above baseline"
    alert_value = f"{hotspot_count}"
    alert_sub = "flagged readings" if hotspot_count else "no flagged readings"
    updated = datetime.now().strftime("%H:%M")

    arrow = (
        f'<svg width="34" height="34" viewBox="0 0 48 48" aria-hidden="true">'
        f'<circle cx="24" cy="24" r="19" fill="none" stroke="rgba(138,170,198,.22)" stroke-width="1"/>'
        f'<g transform="rotate({arrow_rotation:.1f} 24 24)">'
        f'<path d="M24 9 L29.5 22 L24 19.3 L18.5 22 Z" fill="#7fe3c9"/>'
        f'<path d="M24 39 L21 30 L27 30 Z" fill="rgba(127,227,201,.38)"/>'
        f'</g></svg>'
    )

    return (
        _CONDITIONS_CSS
        + '<div class="mt-conditions">'
        + '<div class="mt-conditions__head">'
        + f'<span class="mt-conditions__title"><i class="mt-conditions__dot{dot_class}"></i>Map conditions</span>'
        + f'<span class="mt-conditions__badge{badge_class}">{badge}</span>'
        + '</div>'
        + '<div class="mt-conditions__wind">'
        + f'<div class="mt-wind-icon">{arrow}</div>'
        + '<div>'
        + '<div class="mt-conditions__label">Wind</div>'
        + f'<div class="mt-conditions__value">{wind_value}<small>km/h</small></div>'
        + f'<div class="mt-conditions__sub">{wind_from_text}</div>'
        + '</div></div>'
        + '<div class="mt-conditions__grid">'
        + '<div class="mt-conditions__cell">'
        + '<div class="mt-conditions__label">Temp</div>'
        + f'<div class="mt-conditions__value">{temp_value}<small>&deg;C</small></div>'
        + '<div class="mt-conditions__sub">ambient</div>'
        + '</div>'
        + '<div class="mt-conditions__cell">'
        + '<div class="mt-conditions__label">CH&#8324; peak</div>'
        + f'<div class="mt-conditions__value">{peak_value}<small>ppm</small></div>'
        + f'<div class="mt-conditions__sub">{excess_value or "no readings"}</div>'
        + '</div>'
        + '<div class="mt-conditions__cell">'
        + '<div class="mt-conditions__label">Alerts</div>'
        + f'<div class="mt-conditions__value">{alert_value}</div>'
        + f'<div class="mt-conditions__sub">{alert_sub}</div>'
        + '</div>'
        + '</div>'
        + '<div class="mt-conditions__foot">'
        + f'<span>Chakan industrial zone</span>'
        + f'<span>{asset_count} assets &middot; {updated} IST</span>'
        + '</div>'
        + '</div>'
    )
