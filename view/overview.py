import streamlit as st

from utils import integrations
from utils.pipeline_service import MATCH_TOLERANCE_M, needs_attention, overview_summary, segment_summary
from utils.sensor_state import alert_summary, fleet_readings
from views.common import CONCEPTS, badge, eyebrow, note, status_badge, SYNTHETIC_NOTICE


def render(ctx):
    data = ctx.data
    summary = overview_summary(data.pipelines, data.observations)
    readings = fleet_readings(ctx.state, data.pipelines)
    sensors = alert_summary(readings)

    st.subheader("Overview")
    note(SYNTHETIC_NOTICE)

    c_assets, c_methane, c_sensors, c_risk = st.columns(4)

    with c_assets.container(border=True):
        eyebrow("Operational status")
        st.metric("Pipeline segments", summary["pipeline_total"])
        st.markdown(
            " ".join(status_badge(k, f"{k}: {v}") for k, v in summary["status_counts"].items()),
            unsafe_allow_html=True,
        )
        st.caption("  |  ".join(f"{k}: {v}" for k, v in summary["type_counts"].items()))

    with c_methane.container(border=True):
        eyebrow("Methane anomalies")
        if data.has_observations:
            st.metric("Above threshold", summary["threshold_anomalies"])
            st.metric("Statistical outliers (ML)", summary["ml_anomalies"])
            st.caption(f"{summary['observation_total']} observations; "
                       f"{summary['segments_with_methane_anomalies']} segment(s) with a flagged observation nearby.")
        else:
            st.markdown(badge("Data unavailable", "warn"), unsafe_allow_html=True)
            st.caption("Methane observations could not be loaded.")

    with c_sensors.container(border=True):
        eyebrow("Sensor alerts (simulated)")
        st.metric("Active sensor alerts", sensors["alerts"])
        st.caption(f"{sensors['monitored']} segments monitored. Use the Sensor Monitoring page to run scenarios.")

    with c_risk.container(border=True):
        eyebrow("Pipeline risk")
        available, _ = integrations.risk_engine_status()
        if available:
            st.markdown(badge("Risk engine connected", "ok"), unsafe_allow_html=True)
            st.caption("Select a segment to see its risk assessment.")
        else:
            st.markdown(badge("Not connected", "neutral"), unsafe_allow_html=True)
            st.caption("Risk scores will appear here once the risk engine is integrated.")

    st.markdown("#### Segments with a non-normal signal")
    st.caption("Each signal is shown separately: operational status, methane detections near the segment, and simulated sensor alert.")
    table = needs_attention(segment_summary(data.pipelines, data.observations, readings))
    if table.empty:
        st.info("No segment currently shows a non-normal operational status, methane anomaly or sensor alert.")
    else:
        table = table.sort_values(
            ["sensor_alert", "threshold_anomalies", "ml_outliers"], ascending=False
        ).rename(columns={
            "pipeline_id": "Segment", "type": "Type", "operational_status": "Operational status",
            "observations": "Nearby observations", "max_ppm": "Max ppm",
            "threshold_anomalies": "Above threshold", "ml_outliers": "ML outliers", "sensor_alert": "Sensor alert",
        })
        st.dataframe(
            table, hide_index=True,
            column_config={"Max ppm": st.column_config.NumberColumn(format="%.2f")},
        )
    if data.has_observations:
        st.caption(
            f"{summary['unattributed_observations']} of {summary['observation_total']} observations are farther than "
            f"{MATCH_TOLERANCE_M:g} m from any segment and are not attributed to a pipeline. Attribution reflects "
            "proximity only and does not identify a leak source."
        )

    with st.expander("What the four signals mean"):
        for text in CONCEPTS.values():
            st.markdown(f"- {text}")
