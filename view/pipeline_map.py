import pandas as pd
import streamlit as st

from utils.map_renderer import render_pipeline_map
from utils.pipeline_service import observation_stats, pipeline_observations
from utils.sensor_state import SCENARIO_NORMAL, get_reading
from views.common import eyebrow, render_risk_panel, status_badge


def _fmt(value, unit="", digits=1):
    if value is None:
        return "N/A"
    return f"{value:,.{digits}f}{unit}" if isinstance(value, float) else f"{value}{unit}"


def _coords(c):
    return "N/A" if not c else f"{c[0]:.5f}, {c[1]:.5f}"


def render(ctx):
    data, sel = ctx.data, ctx.selected_id
    st.subheader("Pipeline Map")

    pipelines, observations = data.pipelines, data.observations
    if sel:
        if st.toggle("Show selected segment only", key="map_isolate"):
            pipelines = pipelines[pipelines["pipeline_id"] == sel]
            observations = observations[observations["pipeline_id"] == sel]

    try:
        # The renderer adds columns to what it receives, so pass copies.
        render_pipeline_map(pipelines.copy(), observations.copy())
    except Exception as e:
        st.error(f"The map could not be rendered: {e}")
    st.caption("Line colour shows operational status (green Active, yellow Maintenance, red Leaking). "
               "The heat layer and columns show methane observations; columns mark statistical outliers.")

    if ctx.record is None:
        st.info("Select a pipeline segment in the sidebar to view its details and telemetry.")
        register = data.pipelines.drop(columns=["geometry", "installation_year"], errors="ignore")
        keep = [c for c in ("pipeline_id", "type", "status", "material", "pressure_bar", "depth_m", "installed", "length_m") if c in register.columns]
        st.markdown("#### Segment register")
        st.dataframe(register[keep], hide_index=True)
        return

    rec = ctx.record
    reading = get_reading(ctx.state, sel, rec.get("pressure_bar"))
    obs = pipeline_observations(data.observations, sel)
    stats = observation_stats(obs)

    st.markdown(f"#### Segment {sel}")
    c_details, c_tele, c_meth = st.columns([1.2, 1, 1])

    with c_details:
        eyebrow("Asset details")
        st.markdown(status_badge(rec["status"], f"Operational status: {rec['status']}"), unsafe_allow_html=True)
        rows = [
            ("Type", rec["type"]), ("Material", rec["material"]),
            ("Rated pressure", _fmt(rec["pressure_bar"], " bar")), ("Burial depth", _fmt(rec["depth_m"], " m")),
            ("Installed", _fmt(rec["installation_year"])), ("Length", _fmt(rec["length_m"], " m", 0)),
            ("Start (lat, lon)", _coords(rec["start_coords"])), ("End (lat, lon)", _coords(rec["end_coords"])),
        ]
        st.dataframe(pd.DataFrame(rows, columns=["Attribute", "Value"]).astype(str), hide_index=True)

    with c_tele:
        eyebrow("Sensor telemetry (simulated)")
        anomaly = reading["is_anomaly"]
        st.metric("Pressure", f"{reading['pressure_bar']:.2f} bar",
                  delta=f"{reading['pressure_delta_bar']:+.2f} bar" if anomaly else None)
        st.metric("Flow rate", f"{reading['flow_rate_m3h']:.2f} m³/h",
                  delta=f"{reading['flow_delta_m3h']:+.2f} m³/h" if anomaly else None, delta_color="inverse")
        st.caption(f"Scenario: {reading['scenario']}. Status: {reading['sensor_status']}. "
                   "Change scenarios on the Sensor Monitoring page.")

    with c_meth:
        eyebrow("Methane near segment")
        if not data.has_observations:
            st.caption("Methane observations unavailable.")
        elif stats["count"] == 0:
            st.caption("No observations are attributed to this segment.")
        else:
            st.metric("Nearby observations", stats["count"])
            st.metric("Max concentration", f"{stats['max_ppm']:.2f} ppm")
            st.caption(f"{stats['threshold']} above threshold, {stats['ml']} ML outlier(s).")
        st.divider()
        render_risk_panel(ctx, reading)
