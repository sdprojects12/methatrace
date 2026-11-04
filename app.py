import html
import textwrap
from datetime import datetime

import pandas as pd
import streamlit as st

# Custom module imports
from utils.anomaly_detector import detect_ml_anomalies
from utils.data_loader import load_observations, load_pipelines
from utils.map_renderer import (
    HOTSPOT_PPM,
    compass_label,
    get_map_conditions_html,
    render_pipeline_map,
)
from utils.risk_engine import calculate_risk_scores, fetch_current_weather
from utils.sensor_sim import generate_sensor_readings

# -----------------------------------------------------------------------------
# 1. PAGE CONFIGURATION & CACHING
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="MethaTrace · Chakan Control",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_data(ttl=600)
def cached_fetch_weather():
    """Fetch and cache meteorological data for 10 minutes."""
    try:
        return fetch_current_weather()
    except Exception as e:
        return {"source": "fallback_mock", "error": str(e)}


def html_block(markup: str) -> str:
    """
    Normalise an indented HTML block for st.markdown.

    Streamlit' markdown parser treats deeply indented lines inside an HTML
    block as code, which leaks raw tags into the page. Flattening the
    indentation on every line keeps the markup intact without that risk.
    """
    return "\n".join(
        line.strip() for line in textwrap.dedent(markup).strip().splitlines()
    )


# -----------------------------------------------------------------------------
# 2. GLOBAL DESIGN SYSTEM
# -----------------------------------------------------------------------------
st.markdown(
    """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
  font-family: 'Inter', 'Segoe UI', sans-serif;
  -webkit-font-smoothing: antialiased;
}

.stApp {
  background:
    radial-gradient(1100px 620px at 12% -12%, rgba(42, 83, 112, 0.26), transparent 62%),
    radial-gradient(900px 520px at 92% -4%, rgba(22, 104, 108, 0.14), transparent 56%),
    #070a10;
}

[data-testid="stHeader"] { background: transparent; }
.block-container {
  max-width: 1560px;
  padding-top: 2.1rem;
  padding-bottom: 3.5rem;
}

/* ---------- sidebar ---------- */
[data-testid="stSidebar"] {
  background: linear-gradient(180deg, #0a111b 0%, #070c13 100%);
  border-right: 1px solid rgba(129, 160, 189, 0.12);
}
[data-testid="stSidebar"] .block-container { padding-top: 1.8rem; }
[data-testid="stSidebar"] h2 {
  font-size: 12px !important;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: #8ba2b7;
  font-weight: 600;
}

/* ---------- hero ---------- */
.mt-hero {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
  padding: 2px 0 4px;
}
.mt-eyebrow {
  display: flex;
  align-items: center;
  gap: 9px;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #7f9ab0;
}
.mt-live-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: #48d6b3;
  box-shadow: 0 0 0 4px rgba(72, 214, 179, 0.13);
}
.mt-title {
  margin: 9px 0 7px;
  font-size: clamp(30px, 3.4vw, 43px);
  line-height: 1.02;
  font-weight: 700;
  letter-spacing: -0.035em;
  color: #f3f8fc;
}
.mt-title span { color: #7fe3c9; }
.mt-subtitle {
  margin: 0;
  max-width: 740px;
  font-size: 14px;
  line-height: 1.55;
  color: #8fa6b9;
}
.mt-hero-chips {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  padding-bottom: 5px;
}
.mt-chip {
  padding: 7px 11px;
  border-radius: 999px;
  border: 1px solid rgba(129, 160, 189, 0.16);
  background: rgba(15, 24, 37, 0.62);
  font-size: 10.5px;
  font-weight: 500;
  letter-spacing: 0.04em;
  color: #9cb0c3;
  white-space: nowrap;
}

/* ---------- KPI strip ---------- */
.mt-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 21px 0 19px;
}
.mt-kpi {
  position: relative;
  overflow: hidden;
  padding: 14px 16px 13px;
  border-radius: 14px;
  border: 1px solid rgba(129, 160, 189, 0.14);
  background: linear-gradient(170deg, rgba(17, 28, 43, 0.88), rgba(9, 15, 25, 0.86));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.025);
}
.mt-kpi::after {
  content: "";
  position: absolute;
  top: 0; left: 16px; right: 16px;
  height: 1px;
  background: linear-gradient(90deg, rgba(127, 227, 201, 0.55), transparent 70%);
  opacity: 0.55;
}
.mt-kpi.warn::after { background: linear-gradient(90deg, rgba(255, 177, 71, 0.65), transparent 70%); }
.mt-kpi-label {
  display: block;
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #7b93a8;
}
.mt-kpi-value {
  display: block;
  margin-top: 5px;
  font-size: 25px;
  font-weight: 600;
  letter-spacing: -0.03em;
  line-height: 1.1;
  color: #eef5fb;
}
.mt-kpi-value small {
  margin-left: 4px;
  font-size: 10px;
  font-weight: 500;
  letter-spacing: 0;
  color: #849caf;
}
.mt-kpi-meta {
  display: block;
  margin-top: 3px;
  font-size: 10px;
  color: #6f879b;
}

/* ---------- map stage ---------- */
.st-key-map_stage {
  position: relative;
  border-radius: 22px;
  overflow: hidden;
  border: 1px solid rgba(129, 160, 189, 0.17);
  background: #060a11;
  box-shadow: 0 34px 90px rgba(0, 0, 0, 0.58);
}
.st-key-map_stage [data-testid="stDeckGlJsonChart"] {
  border-radius: 22px;
  overflow: hidden;
}
.st-key-map_stage [data-testid="stElementContainer"]:has(.mt-map-title) {
  position: absolute;
  top: 18px;
  left: 20px;
  z-index: 7;
  width: auto;
  margin: 0 !important;
}
.st-key-map_stage [data-testid="stElementContainer"]:has(.mt-conditions) {
  position: absolute;
  left: 20px;
  bottom: 36px;
  z-index: 7;
  width: auto;
  margin: 0 !important;
}
.mt-map-title {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 9px 13px;
  border-radius: 11px;
  border: 1px solid rgba(138, 170, 198, 0.18);
  background: linear-gradient(165deg, rgba(12, 20, 33, 0.88), rgba(6, 11, 19, 0.82));
  box-shadow: 0 12px 35px rgba(0, 0, 0, 0.35);
  backdrop-filter: blur(14px);
  -webkit-backdrop-filter: blur(14px);
  pointer-events: none;
}
.mt-map-title__kicker {
  display: block;
  font-size: 8.5px;
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  color: #7f9ab0;
}
.mt-map-title__main {
  display: block;
  margin-top: 1px;
  font-size: 14px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: #eef5fb;
}
.mt-map-title__live {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 5px 8px;
  border-radius: 999px;
  border: 1px solid rgba(72, 214, 179, 0.22);
  background: rgba(72, 214, 179, 0.07);
  font-size: 8.5px;
  font-weight: 700;
  letter-spacing: 0.14em;
  color: #7fe3c9;
  text-transform: uppercase;
}
.mt-map-title__live i {
  width: 5px; height: 5px; border-radius: 50%;
  background: #48d6b3;
  box-shadow: 0 0 0 3px rgba(72, 214, 179, 0.14);
}
.mt-map-hint {
  margin: 9px 2px 0;
  font-size: 10px;
  letter-spacing: 0.02em;
  color: #637b90;
}

/* ---------- panels below the map ---------- */
.mt-panel {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 292px;
  padding: 17px 18px 15px;
  border-radius: 16px;
  border: 1px solid rgba(129, 160, 189, 0.14);
  background: linear-gradient(170deg, rgba(16, 26, 41, 0.82), rgba(8, 14, 23, 0.86));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.025);
}
.mt-panel__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(129, 160, 189, 0.12);
}
.mt-panel__title {
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #8fa7bb;
}
.mt-tag {
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid rgba(129, 160, 189, 0.17);
  background: rgba(129, 160, 189, 0.05);
  font-size: 8.5px;
  font-weight: 600;
  letter-spacing: 0.11em;
  color: #8ba2b7;
  text-transform: uppercase;
  white-space: nowrap;
}
.mt-status {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 13px 0 15px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.mt-status i {
  width: 7px; height: 7px; border-radius: 50%;
}
.mt-status.ok { color: #7fe3c9; }
.mt-status.ok i { background: #48d6b3; box-shadow: 0 0 0 4px rgba(72, 214, 179, 0.13); }
.mt-status.alert { color: #ffb147; }
.mt-status.alert i { background: #ffb147; box-shadow: 0 0 0 4px rgba(255, 177, 71, 0.14); }
.mt-telemetry {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 14px;
}
.mt-telemetry > div {
  padding: 12px 13px;
  border-radius: 11px;
  border: 1px solid rgba(129, 160, 189, 0.10);
  background: rgba(6, 11, 19, 0.42);
}
.mt-telemetry span {
  display: block;
  font-size: 8.5px;
  font-weight: 600;
  letter-spacing: 0.14em;
  text-transform: uppercase;
  color: #748da2;
}
.mt-telemetry strong {
  display: block;
  margin-top: 4px;
  font-size: 21px;
  font-weight: 600;
  letter-spacing: -0.025em;
  color: #eef5fb;
}
.mt-telemetry strong small {
  margin-left: 3px;
  font-size: 9.5px;
  font-weight: 500;
  color: #849caf;
}
.mt-telemetry em {
  display: block;
  margin-top: 2px;
  font-size: 10px;
  font-style: normal;
  color: #ffb147;
}
.mt-panel__foot {
  margin-top: auto;
  padding-top: 13px;
  font-size: 9.5px;
  letter-spacing: 0.03em;
  color: #5f778c;
}
.mt-log-row {
  display: flex;
  align-items: flex-start;
  gap: 11px;
  padding: 11px 0;
  border-bottom: 1px solid rgba(129, 160, 189, 0.09);
}
.mt-log-row:last-child { border-bottom: 0; padding-bottom: 2px; }
.mt-log-dot {
  width: 6px; height: 6px; flex: 0 0 6px;
  margin-top: 5px;
  border-radius: 50%;
  background: #627b90;
}
.mt-log-dot.ok { background: #48d6b3; box-shadow: 0 0 0 3px rgba(72, 214, 179, 0.10); }
.mt-log-dot.warn { background: #ffb147; box-shadow: 0 0 0 3px rgba(255, 177, 71, 0.11); }
.mt-log-dot.info { background: #5ba8c9; box-shadow: 0 0 0 3px rgba(91, 168, 201, 0.10); }
.mt-log-row b {
  display: block;
  font-size: 11.5px;
  font-weight: 600;
  color: #dfeaf4;
}
.mt-log-row small {
  display: block;
  margin-top: 2px;
  font-size: 10px;
  line-height: 1.45;
  color: #6f879b;
}

/* ---------- section heading ---------- */
.mt-section-head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
  margin: 26px 0 4px;
}
.mt-section-kicker {
  display: block;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.17em;
  text-transform: uppercase;
  color: #748da2;
}
.mt-section-head h2 {
  margin: 4px 0 0;
  font-size: 21px;
  font-weight: 600;
  letter-spacing: -0.02em;
  color: #eef5fb;
}

/* ---------- dataframe ---------- */
[data-testid="stDataFrame"] {
  border-radius: 14px;
  overflow: hidden;
  border: 1px solid rgba(129, 160, 189, 0.14);
}

@media (max-width: 1100px) {
  .mt-kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .mt-hero { align-items: flex-start; flex-direction: column; gap: 16px; }
  .mt-hero-chips { justify-content: flex-start; }
}
@media (max-width: 760px) {
  .mt-kpis { grid-template-columns: 1fr; }
  .mt-telemetry { grid-template-columns: 1fr; }
  .mt-panel { min-height: 0; }
}
</style>
""",
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# 3. SESSION STATE
# -----------------------------------------------------------------------------
if "rupture_triggered" not in st.session_state:
    st.session_state.rupture_triggered = False

# -----------------------------------------------------------------------------
# 4. SIDEBAR CONTROLS
# -----------------------------------------------------------------------------
st.sidebar.markdown("### Demo controls")
st.sidebar.caption("Inject a live IoT event into the telemetry stream.")

if st.session_state.rupture_triggered:
    if st.sidebar.button("Reset system to normal", type="primary", use_container_width=True):
        st.session_state.rupture_triggered = False
        st.rerun()
else:
    if st.sidebar.button("Trigger pipeline rupture", type="secondary", use_container_width=True):
        st.session_state.rupture_triggered = True
        st.rerun()

# -----------------------------------------------------------------------------
# 5. HERO
# -----------------------------------------------------------------------------
now = datetime.now()
st.markdown(
    f"""
<div class="mt-hero">
  <div>
    <div class="mt-eyebrow"><span class="mt-live-dot"></span>Live monitoring · Chakan industrial zone</div>
    <h1 class="mt-title">MethaTrace <span>Control</span></h1>
    <p class="mt-subtitle">Real-time spatial pipeline intelligence and ML-powered methane anomaly detection.</p>
  </div>
  <div class="mt-hero-chips">
    <span class="mt-chip">Sector 07 · Pune</span>
    <span class="mt-chip">18.75°N · 73.81°E</span>
    <span class="mt-chip">{now:%d %b %Y} · {now:%H:%M} IST</span>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

# -----------------------------------------------------------------------------
# 6. DATA PIPELINE
# -----------------------------------------------------------------------------
pipelines_gdf = load_pipelines()
raw_observations = load_observations()

if pipelines_gdf is not None and raw_observations is not None:
    processed_obs = detect_ml_anomalies(raw_observations)
    weather_data = cached_fetch_weather()
    scored_pipelines = calculate_risk_scores(
        pipelines_gdf, processed_obs, weather_data
    )

    # ----- derived indicators -------------------------------------------------
    ppm = pd.to_numeric(
        processed_obs["methane_concentration_ppm"], errors="coerce"
    ).dropna()
    peak_ppm = float(ppm.max()) if len(ppm) else 0.0
    hotspot_count = int((ppm >= HOTSPOT_PPM).sum())
    anomaly_count = int(processed_obs["is_ml_anomaly"].sum())
    critical_count = int((scored_pipelines["risk_level"] == "High").sum())
    avg_pressure = (
        pd.to_numeric(scored_pipelines["pressure_bar"], errors="coerce").mean()
    )

    # ----- KPI strip ----------------------------------------------------------
    st.markdown(
        f"""
<div class="mt-kpis">
  <div class="mt-kpi">
    <span class="mt-kpi-label">Monitored assets</span>
    <span class="mt-kpi-value">{len(scored_pipelines)}<small>segments</small></span>
    <span class="mt-kpi-meta">Full network under watch</span>
  </div>
  <div class="mt-kpi {'warn' if hotspot_count else ''}">
    <span class="mt-kpi-label">Emission hotspots</span>
    <span class="mt-kpi-value">{hotspot_count}<small>on map</small></span>
    <span class="mt-kpi-meta">{anomaly_count} ML-flagged readings</span>
  </div>
  <div class="mt-kpi">
    <span class="mt-kpi-label">Peak methane</span>
    <span class="mt-kpi-value">{peak_ppm:.1f}<small>ppm</small></span>
    <span class="mt-kpi-meta">Atmospheric baseline 2.0 ppm</span>
  </div>
  <div class="mt-kpi">
    <span class="mt-kpi-label">Network pressure</span>
    <span class="mt-kpi-value">{avg_pressure:.1f}<small>bar</small></span>
    <span class="mt-kpi-meta">{critical_count} critical segments</span>
  </div>
</div>
""",
        unsafe_allow_html=True,
    )

    # ----- MAP ----------------------------------------------------------------
    st.markdown(
        '<div class="mt-section-kicker" style="margin-bottom:8px;">Spatial intelligence</div>',
        unsafe_allow_html=True,
    )

    with st.container(key="map_stage"):
        st.markdown(
            """
<div class="mt-map-title">
  <div>
    <span class="mt-map-title__kicker">Live asset &amp; emission map</span>
    <span class="mt-map-title__main">Chakan pipeline corridor</span>
  </div>
  <span class="mt-map-title__live"><i></i>Live</span>
</div>
""",
            unsafe_allow_html=True,
        )
        deck = render_pipeline_map(scored_pipelines, processed_obs)
        st.pydeck_chart(deck, width="stretch", height=680)
        st.markdown(
            get_map_conditions_html(
                weather=weather_data,
                observations_df=processed_obs,
                pipelines_gdf=scored_pipelines,
                alert=st.session_state.rupture_triggered,
            ),
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div class="mt-map-hint">Drag to pan · Scroll to zoom · Right-drag or ctrl-drag to orbit and tilt</div>',
        unsafe_allow_html=True,
    )

    # ----- TELEMETRY + LOG ----------------------------------------------------
    sensor_data = None
    demo_asset_id = ""
    if not pipelines_gdf.empty:
        demo_asset_id = str(pipelines_gdf.iloc[0]["pipeline_id"])
        sensor_data = generate_sensor_readings(
            demo_asset_id, trigger_anomaly=st.session_state.rupture_triggered
        )

    col_telemetry, col_log = st.columns([1.18, 1], gap="medium")

    with col_telemetry:
        if sensor_data:
            triggered = st.session_state.rupture_triggered
            status_class = "alert" if triggered else "ok"
            status_text = html.escape(
                sensor_data.get("sensor_status", "Normal operations")
            )
            pressure_delta = (
                '<em>−25.4 bar from nominal</em>' if triggered else ""
            )
            flow_delta = (
                '<em>+80.2 m³/h from nominal</em>' if triggered else ""
            )
            st.markdown(
                html_block(
                    f"""
<div class="mt-panel">
  <div class="mt-panel__head">
    <span class="mt-panel__title">Live telemetry</span>
    <span class="mt-tag">{html.escape(demo_asset_id)}</span>
  </div>
  <div class="mt-status {status_class}"><i></i>{status_text}</div>
  <div class="mt-telemetry">
    <div>
      <span>Pressure</span>
      <strong>{sensor_data.get('pressure_bar', 0):.2f}<small>bar</small></strong>
      {pressure_delta}
    </div>
    <div>
      <span>Flow rate</span>
      <strong>{sensor_data.get('flow_rate_m3h', 0):.2f}<small>m³/h</small></strong>
      {flow_delta}
    </div>
  </div>
  <div class="mt-panel__foot">IoT edge node · 1 s sampling · calibrated today</div>
</div>
"""
                ),
                unsafe_allow_html=True,
            )
        else:
            st.warning("No operational assets found in database.")

    with col_log:
        weather_note = (
            "Fallback meteorological model"
            if weather_data.get("source") == "fallback_mock"
            else f"Wind from {compass_label(weather_data.get('wind_direction_deg'))} at "
                 f"{weather_data.get('wind_speed_kmh', 'N/A')} km/h"
        )
        hotspot_note = (
            f"{hotspot_count} readings at or above {HOTSPOT_PPM:.0f} ppm"
            if hotspot_count
            else "No readings above the hotspot threshold"
        )
        st.markdown(
            html_block(
                f"""
<div class="mt-panel">
  <div class="mt-panel__head">
    <span class="mt-panel__title">Condition log</span>
    <span class="mt-tag">Automated</span>
  </div>
  <div class="mt-log-row">
    <span class="mt-log-dot {'warn' if hotspot_count else 'ok'}"></span>
    <div><b>{hotspot_count} emission hotspots on the map</b><small>{hotspot_note}</small></div>
  </div>
  <div class="mt-log-row">
    <span class="mt-log-dot info"></span>
    <div><b>Meteorological feed</b><small>{weather_note}</small></div>
  </div>
  <div class="mt-log-row">
    <span class="mt-log-dot {'warn' if critical_count else 'ok'}"></span>
    <div><b>{critical_count} critical pipeline segments</b><small>Simulated risk score · rule-based prototype</small></div>
  </div>
  <div class="mt-log-row">
    <span class="mt-log-dot ok"></span>
    <div><b>Spatial filter active</b><small>All layers constrained to the Chakan bounding box</small></div>
  </div>
</div>
"""
            ),
            unsafe_allow_html=True,
        )

    # ----- RISK TABLE ---------------------------------------------------------
    st.markdown(
        f"""
<div class="mt-section-head">
  <div>
    <span class="mt-section-kicker">Network intelligence</span>
    <h2>Pipeline risk assessment</h2>
  </div>
  <span class="mt-tag">Simulated model</span>
</div>
""",
        unsafe_allow_html=True,
    )

    disclaimer = scored_pipelines.attrs.get(
        "disclaimer", "Simulated Risk Score for demonstration purposes only."
    )
    st.caption(disclaimer)

    display_cols = [
        "pipeline_id",
        "simulated_risk_score",
        "risk_level",
        "risk_explanation",
    ]
    available_cols = [c for c in display_cols if c in scored_pipelines.columns]

    st.dataframe(
        scored_pipelines[available_cols],
        width="stretch",
        hide_index=True,
        column_config={
            "pipeline_id": st.column_config.TextColumn("Pipeline", width="small"),
            "simulated_risk_score": st.column_config.ProgressColumn(
                "Risk score", min_value=0, max_value=100, format="%.0f"
            ),
            "risk_level": st.column_config.TextColumn("Level", width="small"),
            "risk_explanation": st.column_config.TextColumn(
                "Assessment", width="large"
            ),
        },
    )

else:
    st.error("System failure: could not load spatial data pipelines.")
