"""Shared UI helpers: theme, badges, the per-run context object and the risk/weather panel."""
from __future__ import annotations

import html
from dataclasses import dataclass

import streamlit as st

from utils import integrations
from utils.pipeline_service import pipeline_observations

CSS = """
<style>
.stApp, .stApp p, .stApp li, .stApp label, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stMarkdown {
    font-family: "Segoe UI", Inter, -apple-system, "Helvetica Neue", Roboto, Arial, sans-serif;
}
.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1400px; }
.stApp h2, .stApp h3 { font-weight: 600; letter-spacing: -0.01em; }
.mt-title { font-size: 1.55rem; font-weight: 650; letter-spacing: -0.015em; line-height: 1.2; }
.mt-subtitle { font-size: 0.92rem; opacity: 0.7; margin-top: 0.15rem; }
.mt-eyebrow { text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.09em; opacity: 0.6; font-weight: 600; }
.mt-badge { display: inline-block; padding: 1px 8px; margin: 0 4px 4px 0; border-radius: 3px; font-size: 0.74rem;
            font-weight: 600; border: 1px solid; line-height: 1.5; white-space: nowrap; }
.mt-badge-ok      { color: #2f7d5c; border-color: rgba(47,125,92,.45);  background: rgba(47,125,92,.10); }
.mt-badge-warn    { color: #a36a00; border-color: rgba(163,106,0,.45);  background: rgba(163,106,0,.10); }
.mt-badge-crit    { color: #b24233; border-color: rgba(178,66,51,.45);  background: rgba(178,66,51,.10); }
.mt-badge-neutral { color: #64748b; border-color: rgba(100,116,139,.45); background: rgba(100,116,139,.10); }
.mt-note { border-left: 3px solid rgba(100,116,139,.6); padding: .55rem .9rem; background: rgba(100,116,139,.08);
           font-size: .85rem; border-radius: 0 3px 3px 0; margin: .25rem 0 1rem 0; }
[data-testid="stMetric"] { padding: .15rem 0; }
[data-testid="stMetricLabel"] p { font-size: .8rem; opacity: .75; }
section[data-testid="stSidebar"] .mt-title { font-size: 1.25rem; }
</style>
"""

# One-line definitions of the four signals the dashboard keeps separate.
CONCEPTS = {
    "operational": "Operational status is the asset-register state of a segment (Active, Maintenance, Leaking). "
                   "It is not a risk score or a measurement.",
    "methane": "Methane anomalies are observation-level detections: concentration above the ppm threshold, "
               "and statistical outliers found by an Isolation Forest model.",
    "sensor": "Sensor anomalies are simulated pressure and flow deviations on a segment. "
              "They are independent of methane observations and operational status.",
    "risk": "Pipeline risk is computed by the risk engine (utils/risk_engine.py).",
}

SYNTHETIC_NOTICE = (
    "All pipeline, methane and sensor data shown here is synthetic and simulated for demonstration. "
    "It does not represent real infrastructure, emissions or field measurements."
)

STATUS_TONES = {"Active": "ok", "Maintenance": "warn", "Leaking": "crit"}


@dataclass
class AppContext:
    data: object            # utils.dashboard_data.DashboardData
    selected_id: str        # None when no segment is selected
    record: dict            # pipeline_record() of the selection, or None
    state: object           # st.session_state


def inject_theme() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def badge(text: str, tone: str = "neutral") -> str:
    return f'<span class="mt-badge mt-badge-{tone}">{html.escape(str(text))}</span>'


def status_badge(status: str, text: str = None) -> str:
    return badge(text or status, STATUS_TONES.get(status, "neutral"))


def note(text: str) -> None:
    st.markdown(f'<div class="mt-note">{html.escape(text)}</div>', unsafe_allow_html=True)


def eyebrow(text: str) -> None:
    st.markdown(f'<div class="mt-eyebrow">{html.escape(text)}</div>', unsafe_allow_html=True)


def pick_pipeline_prompt(what: str) -> None:
    st.info(f"Select a pipeline segment in the sidebar to {what}.")


@st.cache_data(ttl=600, show_spinner=False)
def _cached_weather(latitude: float, longitude: float):
    return integrations.get_weather(latitude, longitude)


def current_risk(ctx: AppContext, reading: dict = None) -> integrations.RiskResult:
    """Risk for the selected segment via the integration layer (never raises)."""
    if ctx.record is None:
        return integrations.RiskResult(integrations.STATUS_UNAVAILABLE, message="No segment selected.")
    weather = None
    if ctx.record.get("start_coords") and integrations.weather_status()[0]:
        result = _cached_weather(*ctx.record["start_coords"])
        weather = result.data if result.available else None
    obs = pipeline_observations(ctx.data.observations, ctx.selected_id)
    return integrations.assess_risk(ctx.record, obs, reading, weather)


def render_risk_panel(ctx: AppContext, reading: dict = None) -> None:
    eyebrow("Pipeline risk")
    if ctx.record is None:
        st.caption("Select a segment to view its risk assessment.")
        return
    risk = current_risk(ctx, reading)
    if risk.available:
        parts = [p for p in (risk.level, None if risk.score is None else f"score {risk.score:g}") if p]
        st.markdown(badge(", ".join(parts) or "Assessed", "neutral"), unsafe_allow_html=True)
        for factor in risk.factors:
            st.caption(f"- {factor}")
    elif risk.status == integrations.STATUS_ERROR:
        st.markdown(badge("Risk engine error", "warn"), unsafe_allow_html=True)
        st.caption(risk.message)
    else:
        st.markdown(badge("Not connected", "neutral"), unsafe_allow_html=True)
        st.caption("The risk engine is not connected yet. A score and contributing factors will appear "
                   "here once utils/risk_engine.py is available.")
