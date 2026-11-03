import streamlit as st

from utils.anomaly_detector import CONTAMINATION, FEATURES
from utils.pipeline_service import (
    MATCH_TOLERANCE_M, METHANE_THRESHOLD_PPM, detection_category, observation_stats, pipeline_observations,
)
from views.common import CONCEPTS, note


def render(ctx):
    data = ctx.data
    st.subheader("Methane Intelligence")
    st.caption(CONCEPTS["methane"])

    if not data.has_observations:
        st.warning("Methane observations are unavailable, so this section has nothing to display. "
                   "Generate the dataset with scripts/generate_synthetic_data.py and reload.")
        return

    obs = data.observations
    scope = "All observations"
    if ctx.selected_id:
        scope = st.radio("Scope", ["All observations", f"Selected segment ({ctx.selected_id})"], horizontal=True)
        if scope != "All observations":
            obs = pipeline_observations(obs, ctx.selected_id)
    else:
        st.caption("Showing all observations. Select a segment in the sidebar to focus on one.")

    stats = observation_stats(obs)
    if stats["count"] == 0:
        st.info("No observations are attributed to the selected segment.")
        return

    cols = st.columns(5)
    cols[0].metric("Observations", stats["count"])
    cols[1].metric(f"Above {METHANE_THRESHOLD_PPM:g} ppm", stats["threshold"])
    cols[2].metric("ML outliers", stats["ml"])
    cols[3].metric("Flagged by both", stats["both"])
    cols[4].metric("Max concentration", f"{stats['max_ppm']:.2f} ppm")

    plot = obs.assign(detection=detection_category(obs))
    left, right = st.columns([2, 1])
    with left:
        st.markdown("#### Concentration over time")
        st.scatter_chart(plot, x="timestamp", y="methane_concentration_ppm", color="detection")
    with right:
        st.markdown("#### Observations by source label")
        st.bar_chart(plot["source_label"].value_counts() if "source_label" in plot.columns else plot["detection"].value_counts())

    st.markdown("#### Flagged observations")
    flagged = plot[plot["detection"] != "Not flagged"]
    if flagged.empty:
        st.info("No observations in this scope were flagged by either detection method.")
    else:
        cols_show = [c for c in ("observation_id", "timestamp", "methane_concentration_ppm", "wind_speed_kmh",
                                 "source_label", "detection", "pipeline_id", "distance_m") if c in flagged.columns]
        st.dataframe(
            flagged.sort_values("methane_concentration_ppm", ascending=False)[cols_show],
            hide_index=True,
            column_config={
                "methane_concentration_ppm": st.column_config.NumberColumn("ppm", format="%.2f"),
                "distance_m": st.column_config.NumberColumn("distance to segment (m)", format="%.0f"),
            },
        )
        st.caption(f"pipeline_id is the nearest segment within {MATCH_TOLERANCE_M:g} m (proximity only; "
                   "blank means no segment is that close).")

    with st.expander("Detection methods"):
        st.markdown(
            f"- **Threshold:** concentration above {METHANE_THRESHOLD_PPM:g} ppm, as documented in data/README.md.\n"
            f"- **ML outlier:** Isolation Forest over {', '.join(FEATURES)} with a fixed contamination of "
            f"{CONTAMINATION:.0%}, so about one in ten observations is always flagged. Treat this as a count of "
            "statistical outliers, not confirmed leaks."
        )
