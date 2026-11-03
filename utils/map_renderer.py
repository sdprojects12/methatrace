import pydeck as pdk
import pandas as pd
import geopandas as gpd
import streamlit as st
import json

def get_status_color(status: str) -> list:
    if status == 'Active': return [0, 255, 127, 255]
    elif status == 'Maintenance': return [255, 215, 0, 255]
    elif status == 'Leaking': return [255, 49, 49, 255]
    return [100, 100, 100, 200]

def get_severity_color(ppm: float) -> list:
    if ppm < 12: return [255, 215, 0, 220]     # Yellow
    elif ppm < 30: return [255, 140, 0, 240]   # Orange
    else: return [255, 0, 0, 255]              # Red

def render_pipeline_map(pipelines_gdf: gpd.GeoDataFrame, observations_df: pd.DataFrame):
    pipelines_gdf['color'] = pipelines_gdf['status'].apply(get_status_color)
    pipelines_gdf['width'] = pipelines_gdf['type'].apply(lambda x: 12 if x == 'Main Trunk' else 4)
    pipeline_json = json.loads(pipelines_gdf.to_json())
    
    # Layer 1: Infrastructure
    pipeline_layer = pdk.Layer(
        "GeoJsonLayer",
        pipeline_json,
        pickable=True,
        stroked=True,
        filled=False,
        get_line_color="properties.color", 
        get_line_width="properties.width",
        line_width_scale=2,
        line_width_min_pixels=1,
    )
    
    # Layer 2: Gaseous Plume Heatmap (Simulates the spreading cloud)
    heatmap_layer = pdk.Layer(
        "HeatmapLayer",
        observations_df,
        opacity=0.4,
        get_position=["longitude", "latitude"],
        get_weight="methane_concentration_ppm",
        radius_pixels=90,
        color_range=[
            [0, 0, 0, 0],          # Transparent baseline
            [255, 215, 0, 100],    # Light Yellow
            [255, 140, 0, 150],    # Orange
            [255, 0, 0, 200]       # Red center
        ]
    )

    # Layer 3: 3D Pillars (Marks the exact high-density source)
    anomalies_df = observations_df[observations_df['is_ml_anomaly'] == True].copy()
    anomalies_df['pillar_color'] = anomalies_df['methane_concentration_ppm'].apply(get_severity_color)
    
    column_layer = pdk.Layer(
        "ColumnLayer",
        anomalies_df,
        get_position=["longitude", "latitude"],
        get_elevation="methane_concentration_ppm",
        elevation_scale=60, 
        radius=90,
        get_fill_color="pillar_color",
        pickable=True,
        auto_highlight=True,
        extruded=True,
        material={"ambient": 0.3, "diffuse": 0.8, "shininess": 40, "specularColor": [255, 255, 255]}
    )

    view_state = pdk.ViewState(
        latitude=18.750, 
        longitude=73.810, 
        zoom=11.7, 
        pitch=50,
        bearing=35 # Angled to show the wind direction stretch
    )

    # SCADA-Grade Tooltip
    tooltip_html = """
    <div style='font-family: "Courier New", Courier, monospace; font-size: 12px; line-height: 1.5;'>
        <div style='background-color: #333; padding: 4px; text-align: center; border-bottom: 1px solid #666;'>
            <b style='color: #00FF00;'>METHA-TRACE TELEMETRY</b>
        </div>
        <div style='padding: 8px;'>
            <b>Asset ID:</b> {pipeline_id}<br/>
            <b>Type:</b> {type}<br/>
            <b>Status:</b> {status}<br/>
            <hr style='border: 0; border-top: 1px dashed #666; margin: 4px 0;'/>
            <b>Operating Pressure:</b> {pressure_bar} Bar<br/>
            <b>Burial Depth:</b> {depth_m} m<br/>
            <b>Installed:</b> {installed}
        </div>
    </div>
    """

    r = pdk.Deck(
        layers=[heatmap_layer, pipeline_layer, column_layer],
        initial_view_state=view_state,
        map_provider="carto",
        map_style="dark",
        tooltip={"html": tooltip_html, "style": {"backgroundColor": "#1A1A1A", "color": "#FFF", "border": "1px solid #444", "padding": "0"}}
    )
    
    st.pydeck_chart(r, use_container_width=True)