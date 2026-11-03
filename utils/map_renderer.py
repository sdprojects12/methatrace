import pydeck as pdk
import pandas as pd
import geopandas as gpd
import streamlit as st
import json

def get_status_color(status: str) -> list:
    if status == 'Active': return [0, 255, 127, 220]       # Neon Green
    elif status == 'Maintenance': return [255, 215, 0, 220] # Bright Gold
    elif status == 'Leaking': return [255, 0, 50, 255]      # Crimson Red
    return [100, 100, 100, 150]

def render_pipeline_map(pipelines_gdf: gpd.GeoDataFrame, observations_df: pd.DataFrame):
    # 1. Neon Pipeline Infrastructure
    pipelines_gdf['color'] = pipelines_gdf['status'].apply(get_status_color)
    pipelines_gdf['width'] = pipelines_gdf['type'].apply(lambda x: 12 if x == 'Main Trunk' else 4)
    pipeline_json = json.loads(pipelines_gdf.to_json())
    
    pipeline_layer = pdk.Layer(
        "GeoJsonLayer",
        pipeline_json,
        stroked=True,
        filled=False,
        get_line_color="properties.color", 
        get_line_width="properties.width",
        line_width_scale=2,
    )
    
    # 2. Cinematic 3D Hexagon Matrix (Replaces the blurry heatmap)
    hex_layer = pdk.Layer(
        "HexagonLayer",
        observations_df,
        get_position=["longitude", "latitude"],
        get_weight="methane_concentration_ppm",
        radius=250,
        elevation_scale=15,
        elevation_range=[0, 1500],
        extruded=True,
        coverage=0.85,
        color_range=[
            [10, 25, 50, 180],     # Dark Sci-Fi Blue (Safe)
            [0, 120, 200, 200],    # Bright Blue
            [255, 215, 0, 220],    # Gold (Warning)
            [255, 100, 0, 240],    # Neon Orange (Danger)
            [255, 0, 50, 255]      # Crimson (Critical)
        ],
        material={"ambient": 0.5, "diffuse": 0.7, "shininess": 100, "specularColor": [255, 255, 255]}
    )

    # 3. Solid 3D Anomaly Pillars
    anomalies_df = observations_df[observations_df['is_ml_anomaly'] == True].copy()
    
    pillar_layer = pdk.Layer(
        "ColumnLayer",
        anomalies_df,
        get_position=["longitude", "latitude"],
        get_elevation="methane_concentration_ppm",
        elevation_scale=80, 
        radius=100,
        get_fill_color=[255, 0, 0, 255],
        extruded=True,
        auto_highlight=True,
        pickable=True,
        material={"ambient": 0.7, "diffuse": 0.9, "shininess": 120, "specularColor": [255, 255, 255]}
    )

    # 4. Wind Trajectory Arcs (Visualizing gas blowing Northeast)
    anomalies_df['downwind_lon'] = anomalies_df['longitude'] + 0.025
    anomalies_df['downwind_lat'] = anomalies_df['latitude'] + 0.025
    
    arc_layer = pdk.Layer(
        "ArcLayer",
        data=anomalies_df,
        get_source_position=["longitude", "latitude"],
        get_target_position=["downwind_lon", "downwind_lat"],
        get_source_color=[255, 0, 50, 255],
        get_target_color=[255, 150, 0, 50],  # Fades out as it blows away
        get_width=6,
        get_tilt=15,
    )

    # 5. Isometric Fly-Over Camera
    view_state = pdk.ViewState(
        latitude=18.750, 
        longitude=73.805, 
        zoom=11.3, 
        pitch=65,       # Extreme cinematic tilt
        bearing=35      # Rotated to face the wind direction
    )

    r = pdk.Deck(
        layers=[hex_layer, pipeline_layer, arc_layer, pillar_layer],
        initial_view_state=view_state,
        map_provider="carto",
        map_style="dark",
        tooltip={
            "html": "<b style='color:#00FF00;'>CRITICAL BREACH DETECTED</b><br/><b>PPM:</b> {methane_concentration_ppm}",
            "style": {"backgroundColor": "#0A0A0A", "color": "#FFF", "border": "1px solid #FF0033"}
        }
    )
    
    st.pydeck_chart(r, width='stretch')