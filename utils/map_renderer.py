import pydeck as pdk
import pandas as pd
import geopandas as gpd
import streamlit as st

def get_status_color(status: str) -> list:
    if status == 'Active':
        return [46, 204, 113, 200]    # Green
    elif status == 'Maintenance':
        return [241, 196, 15, 200]    # Yellow
    elif status == 'Leaking':
        return [231, 76, 60, 255]     # Red
    return [149, 165, 166, 200]       # Gray fallback

def render_pipeline_map(pipelines_gdf: gpd.GeoDataFrame, observations_df: pd.DataFrame):
    pipelines_gdf['color'] = pipelines_gdf['status'].apply(get_status_color)
    
    pipeline_layer = pdk.Layer(
        "GeoJsonLayer",
        pipelines_gdf,
        pickable=True,
        stroked=True,
        filled=False,
        get_line_color="color",
        get_line_width=15,
        line_width_min_pixels=4,
    )
    
    anomalies_df = observations_df[observations_df['is_ml_anomaly'] == True]
    
    hotspot_layer = pdk.Layer(
        "ScatterplotLayer",
        anomalies_df,
        pickable=True,
        opacity=0.5,
        filled=True,
        radius_scale=1,
        radius_min_pixels=6,
        radius_max_pixels=20,
        get_position=["longitude", "latitude"],
        get_fill_color=[255, 140, 0, 220],
    )

    view_state = pdk.ViewState(
        latitude=18.75, 
        longitude=73.85, 
        zoom=11, 
        pitch=40 
    )

    r = pdk.Deck(
        layers=[pipeline_layer, hotspot_layer],
        initial_view_state=view_state,
        map_style="mapbox://styles/mapbox/dark-v11",
        tooltip={
            "html": "<b>Asset ID:</b> {pipeline_id} <br/> <b>Status:</b> {status} <br/> <b>Material:</b> {material}",
            "style": {"backgroundColor": "#2C3E50", "color": "#ECF0F1"}
        }
    )
    
    st.pydeck_chart(r)