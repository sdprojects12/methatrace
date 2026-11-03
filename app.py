import streamlit as st
from utils.risk_engine import fetch_current_weather, calculate_risk_scores
from utils.data_loader import load_pipelines, load_observations
from utils.anomaly_detector import detect_ml_anomalies
from utils.map_renderer import render_pipeline_map
from utils.sensor_sim import generate_sensor_readings

# 1. Page Configuration
st.set_page_config(page_title="MethaTrace Dashboard", layout="wide", page_icon="🌍")

st.title("🌍 MethaTrace: Chakan Industrial Zone")
st.markdown("Real-time spatial pipeline monitoring and ML-powered methane anomaly detection.")

# 2. Sidebar Controls
st.sidebar.header("Demo Control Panel")
trigger_alert = st.sidebar.button("🚨 Trigger IoT Pipeline Rupture")

# 3. Load Data
pipelines_gdf = load_pipelines()
raw_observations = load_observations()

if pipelines_gdf is not None and raw_observations is not None:
    # --- RUN ML & RISK ENGINE FIRST ---
    processed_obs = detect_ml_anomalies(raw_observations)
    
    @st.cache_data(ttl=600)
    def get_weather():
        return fetch_current_weather()
        
    weather_data = get_weather()
    
    # Score the pipelines so the map can color them by risk
    scored_pipelines = calculate_risk_scores(pipelines_gdf, processed_obs, weather_data)

    # --- UI LAYOUT ---
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("Live Asset & Emission Map")
        # Claude's upgraded map now accepts weather_data to drive the 3D wind arcs
        deck = render_pipeline_map(scored_pipelines, processed_obs, weather=weather_data)
        st.pydeck_chart(deck, width='stretch')
        
    with col2:
        st.subheader("IoT Telemetry")
        demo_asset_id = pipelines_gdf.iloc[0]['pipeline_id']
        st.write(f"**Target Asset:** `{demo_asset_id}`")
        
        sensor_data = generate_sensor_readings(demo_asset_id, trigger_anomaly=trigger_alert)
        if trigger_alert:
            st.error(sensor_data['sensor_status'])
            st.metric(label="Pressure", value=f"{sensor_data['pressure_bar']} Bar", delta="-25.4 Bar", delta_color="inverse")
            st.metric(label="Flow Rate", value=f"{sensor_data['flow_rate_m3h']} m³/h", delta="+80.2 m³/h", delta_color="inverse")
        else:
            st.success(sensor_data['sensor_status'])
            st.metric(label="Pressure", value=f"{sensor_data['pressure_bar']} Bar")
            st.metric(label="Flow Rate", value=f"{sensor_data['flow_rate_m3h']} m³/h")
            
        st.divider()
        st.subheader("System Logs")
        anomaly_count = processed_obs['is_ml_anomaly'].sum()
        st.warning(f"AI Engine detected **{anomaly_count}** critical emission hotspots.")

        if weather_data.get("source") == "fallback_mock":
            st.warning("Weather API offline. Using simulated meteorological data.")
        else:
            st.info(f"Live Weather (Chakan Hub): {weather_data.get('temperature_c', 'N/A')}°C | Wind: {weather_data.get('wind_direction_deg', 'N/A')}° at {weather_data.get('wind_speed_kmh', 'N/A')} km/h")

    # --- RISK TABLE ---
    st.divider()
    st.markdown("### ⚠️ Pipeline Risk Assessment")
    st.caption(scored_pipelines.attrs.get("disclaimer", "Simulated Risk Score for demonstration purposes only."))
    st.dataframe(
        scored_pipelines[["pipeline_id", "simulated_risk_score", "risk_level", "risk_explanation"]], 
        use_container_width=True,
        hide_index=True
    )
else:
    st.error("System Failure: Could not load data pipeline.")