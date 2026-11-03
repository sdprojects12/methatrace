import pandas as pd
import streamlit as st

from utils import sensor_state as ss
from views.common import CONCEPTS, badge, eyebrow, note, pick_pipeline_prompt


def _on_scenario_change(pipeline_id: str):
    ss.set_scenario(st.session_state, pipeline_id, st.session_state[f"scenario_radio_{pipeline_id}"])


def _fleet_table(readings: dict, alerts_only: bool) -> pd.DataFrame:
    rows = [
        {"Segment": pid, "Scenario": r["scenario"], "Pressure (bar)": r["pressure_bar"],
         "Flow (m³/h)": r["flow_rate_m3h"], "Sensor status": r["sensor_status"], "Alert": r["is_anomaly"]}
        for pid, r in readings.items() if r["is_anomaly"] or not alerts_only
    ]
    return pd.DataFrame(rows)


def render(ctx):
    data, sel = ctx.data, ctx.selected_id
    st.subheader("Sensor Monitoring")
    st.caption(CONCEPTS["sensor"])
    note("Readings are simulated and kept stable between page interactions. Running a scenario changes sensor "
         "telemetry only; it does not alter methane observations, operational status or risk.")

    readings = ss.fleet_readings(ctx.state, data.pipelines)

    if sel is None:
        pick_pipeline_prompt("run a sensor scenario and view its readings")
    else:
        rec = ctx.record
        reading = readings[sel]
        st.markdown(f"#### Segment {sel}")

        radio_key = f"scenario_radio_{sel}"
        st.session_state[radio_key] = ss.get_scenario(ctx.state, sel)
        controls, _ = st.columns([2, 1])
        with controls:
            st.radio("Simulation scenario", ss.SCENARIOS, key=radio_key, horizontal=True,
                     on_change=_on_scenario_change, args=(sel,))
            b1, b2 = st.columns(2)
            b1.button("Generate new baseline reading", on_click=ss.regenerate, args=(ctx.state, sel))
            b2.button("Reset all scenarios", on_click=ss.reset_all, args=(ctx.state,))

        anomaly = reading["is_anomaly"]
        m1, m2, m3 = st.columns(3)
        m1.metric("Pressure", f"{reading['pressure_bar']:.2f} bar",
                  delta=f"{reading['pressure_delta_bar']:+.2f} bar vs baseline" if anomaly else None)
        m2.metric("Flow rate", f"{reading['flow_rate_m3h']:.2f} m³/h",
                  delta=f"{reading['flow_delta_m3h']:+.2f} m³/h vs baseline" if anomaly else None,
                  delta_color="inverse")
        with m3:
            eyebrow("Sensor status")
            st.markdown(badge(reading["sensor_status"], "crit" if anomaly else "ok"), unsafe_allow_html=True)
            rated = rec.get("pressure_bar") if rec else None
            if rated:
                st.caption(f"{reading['pressure_bar'] / rated * 100:.0f}% of the segment's rated pressure ({rated:g} bar).")
            st.caption(f"Reading generated {reading['generated_at'].replace('T', ' ')} UTC (simulated).")

    st.markdown("#### All segments")
    summary = ss.alert_summary(readings)
    alerts_only = st.checkbox("Show only segments with a sensor alert", value=True)
    table = _fleet_table(readings, alerts_only)
    if table.empty:
        st.info("No sensor anomalies in the current simulation. Select a segment and choose the "
                "pressure-drop scenario to simulate one.")
    else:
        st.dataframe(table, hide_index=True)
    st.caption(f"{summary['alerts']} alert(s) across {summary['monitored']} monitored segments.")
