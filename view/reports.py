import streamlit as st

from utils.pipeline_service import anomaly_info, pipeline_observations
from utils.report_builder import build_pdf, recommendations_for
from utils.sensor_state import get_reading
from views.common import SYNTHETIC_NOTICE, current_risk, note, pick_pipeline_prompt


def render(ctx):
    data, sel = ctx.data, ctx.selected_id
    st.subheader("Reports")
    note(SYNTHETIC_NOTICE + " Generated reports carry the same disclaimer.")

    if sel is None:
        pick_pipeline_prompt("generate an inspection report for it")
        return

    rec = ctx.record
    reading = get_reading(ctx.state, sel, rec.get("pressure_bar"))
    obs = pipeline_observations(data.observations, sel)
    info = anomaly_info(obs)
    risk = current_risk(ctx, reading)

    st.markdown(f"#### Inspection report: {sel}")
    st.caption("The report reflects the current state of the dashboard for this segment, including the "
               "sensor scenario shown below.")
    c1, c2, c3 = st.columns(3)
    c1.metric("Operational status", rec["status"])
    c2.metric("Sensor scenario", reading["scenario"])
    c3.metric("Nearby observations", len(obs))

    st.markdown("**Contents**")
    st.markdown(
        f"- Segment details: {rec['type']}, {rec['material']}, installed {rec['installation_year'] or 'N/A'}\n"
        f"- Simulated sensor readings: {reading['pressure_bar']:.2f} bar, {reading['flow_rate_m3h']:.2f} m³/h "
        f"({reading['sensor_status']})\n"
        f"- Methane anomaly counts: {info['threshold_anomaly_count']} above threshold, "
        f"{info['ml_anomaly_count']} ML outlier(s)\n"
        f"- Pipeline risk: {'included in recommendations' if risk.available else 'not included (risk engine not connected)'}\n"
        "- Data provenance and synthetic-data disclaimer"
    )
    with st.expander("Recommendations to be included"):
        for r in recommendations_for(rec, reading, obs, risk):
            st.markdown(f"- {r}")

    try:
        report_id, pdf = build_pdf(sel, data, reading, risk)
    except ModuleNotFoundError as e:
        st.error(f"PDF generation needs the '{e.name}' package. Install it with: pip install -r requirements.txt")
        return
    except Exception as e:
        st.error(f"The report could not be generated: {type(e).__name__}: {e}")
        return

    st.download_button(
        "Download PDF report", data=pdf, file_name=f"{report_id}.pdf", mime="application/pdf",
    )
    st.caption(f"Report ID {report_id}  |  {len(pdf) / 1024:.1f} KB")
