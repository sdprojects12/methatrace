import streamlit as st
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

# 3. Load and Process Data (Yash's Backend)
pipelines_gdf = load_pipelines()
raw_observations = load_observations()

if pipelines_gdf is not None and raw_observations is not None:
    # Run Isolation Forest ML to find hotspots
    processed_obs = detect_ml_anomalies(raw_observations)
    
    # 4. Dashboard Layout (Map left, Sensors right)
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("Live Asset & Emission Map")
        # Render PyDeck Map (Sarvesh's Frontend)
        render_pipeline_map(pipelines_gdf, processed_obs)
        
    with col2:
        st.subheader("IoT Telemetry")
        # Pick the first pipeline to act as our demo asset
        demo_asset_id = pipelines_gdf.iloc[0]['pipeline_id']
        st.write(f"**Target Asset:** `{demo_asset_id}`")
        
        # Get simulated readings (Sarvesh's Frontend)
        sensor_data = generate_sensor_readings(demo_asset_id, trigger_anomaly=trigger_alert)
        
        # Display colored metrics based on status
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
else:
    st.error("System Failure: Could not load data pipeline.")