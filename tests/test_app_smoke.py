"""Headless end-to-end tests of app.py using Streamlit's AppTest."""
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from utils import data_loader

APP_PATH = str(Path(__file__).resolve().parent.parent / "app.py")
PAGES = ["Overview", "Pipeline Map", "Methane Intelligence", "Sensor Monitoring", "Reports"]
SEGMENT = "DIST-0068"  # a real, non-first segment in the synthetic dataset


@pytest.fixture(autouse=True)
def fresh_cache():
    st.cache_data.clear()
    yield
    st.cache_data.clear()


def new_app() -> AppTest:
    return AppTest.from_file(APP_PATH, default_timeout=90).run()


def go(at: AppTest, page: str) -> AppTest:
    return at.sidebar.radio(key="nav_page").set_value(page).run()


def select(at: AppTest, pipeline_id: str) -> AppTest:
    return at.sidebar.selectbox(key="selected_pipeline").select(pipeline_id).run()


def assert_clean(at: AppTest):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_without_selection(page):
    at = go(new_app(), page)
    assert_clean(at)


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_with_selection(page):
    at = select(new_app(), SEGMENT)
    assert_clean(go(at, page))


def test_no_pipeline_is_preselected():
    at = new_app()
    assert at.sidebar.selectbox(key="selected_pipeline").value is None


def test_overview_counts_come_from_data():
    at = new_app()
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Pipeline segments"] == "132"
    assert metrics["Above threshold"] == "3"
    assert metrics["Active sensor alerts"] == "0"


def test_selection_drives_details_and_report():
    at = select(new_app(), SEGMENT)
    at = go(at, "Reports")
    assert any(SEGMENT in m.value for m in at.markdown)
    assert {m.label: m.value for m in at.metric}["Operational status"] == "Leaking"


def test_sensor_readings_stable_across_reruns_and_reflected_everywhere():
    at = go(select(new_app(), SEGMENT), "Sensor Monitoring")
    before = [(m.label, m.value) for m in at.metric]
    at.run()
    assert [(m.label, m.value) for m in at.metric] == before  # unrelated rerun changes nothing

    at.radio(key=f"scenario_radio_{SEGMENT}").set_value("Pressure-drop anomaly").run()
    assert_clean(at)
    assert any("CRITICAL" in m.value for m in at.markdown)
    pressure = {m.label: m.value for m in at.metric}["Pressure"]

    at = go(at, "Overview")
    assert {m.label: m.value for m in at.metric}["Active sensor alerts"] == "1"
    at = go(at, "Reports")
    assert {m.label: m.value for m in at.metric}["Sensor scenario"] == "Pressure-drop anomaly"
    at = go(at, "Pipeline Map")
    assert {m.label: m.value for m in at.metric}["Pressure"] == pressure


def test_demo_button_triggers_anomaly_and_clear_resets():
    at = select(new_app(), SEGMENT)
    next(b for b in at.sidebar.button if b.label.startswith("Simulate pressure-drop")).click().run()
    assert {m.label: m.value for m in go(at, "Overview").metric}["Active sensor alerts"] == "1"
    next(b for b in at.sidebar.button if b.label == "Clear simulated anomalies").click().run()
    assert {m.label: m.value for m in at.metric}["Active sensor alerts"] == "0"


def test_reports_page_has_download_button_only_with_selection():
    assert not go(new_app(), "Reports").get("download_button")
    at = go(select(new_app(), SEGMENT), "Reports")
    buttons = at.get("download_button")
    assert len(buttons) == 1 and buttons[0].proto.label == "Download PDF report"
    assert any("synthetic" in m.value.lower() for m in at.markdown)


def test_report_failure_is_reported_not_raised(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("renderer exploded")
    monkeypatch.setattr("views.reports.build_pdf", boom)
    at = go(select(new_app(), SEGMENT), "Reports")
    assert not at.exception
    assert any("could not be generated" in e.value for e in at.error)
    assert not at.get("download_button")


def test_missing_datasets_show_error_and_stop(monkeypatch, tmp_path):
    monkeypatch.setattr(data_loader, "PIPELINES_FILE", str(tmp_path / "missing.geojson"))
    monkeypatch.setattr(data_loader, "OBSERVATIONS_FILE", str(tmp_path / "missing.csv"))
    at = new_app()
    assert not at.exception
    assert any("not found" in e.value for e in at.error)


def test_missing_observations_degrades_gracefully(monkeypatch, tmp_path):
    monkeypatch.setattr(data_loader, "OBSERVATIONS_FILE", str(tmp_path / "missing.csv"))
    at = new_app()
    assert any("Methane observations unavailable" in w.value for w in at.warning)
    for page in PAGES:
        at = go(at, page)
        assert not at.exception, page
    assert not at.error
