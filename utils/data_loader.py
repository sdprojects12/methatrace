import os
import pandas as pd
import geopandas as gpd
import streamlit as st

# Resolve absolute paths relative to this utility script
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

PIPELINES_FILE = os.path.join(DATA_DIR, 'chakan_pipelines.geojson')
OBSERVATIONS_FILE = os.path.join(DATA_DIR, 'methane_observations.csv')

@st.cache_data
def load_pipelines():
    """
    Loads synthetic pipeline GeoJSON data for the Chakan area.
    Returns a GeoDataFrame.
    """
    try:
        pipelines_gdf = gpd.read_file(PIPELINES_FILE)
        print("Loaded synthetic pipeline data.")
        return pipelines_gdf
    except FileNotFoundError:
        st.error(f"Pipeline data file not found at {PIPELINES_FILE}. Run the generation script first.")
        return None
    except Exception as e:
        st.error(f"Error loading pipeline data: {e}")
        return None

@st.cache_data
def load_observations():
    """
    Loads synthetic methane observation CSV data.
    Returns a Pandas DataFrame with parsed datetime.
    """
    try:
        obs_df = pd.read_csv(OBSERVATIONS_FILE)
        obs_df['timestamp'] = pd.to_datetime(obs_df['timestamp'])
        print("Loaded synthetic observation data.")
        return obs_df
    except FileNotFoundError:
        st.error(f"Observation data file not found at {OBSERVATIONS_FILE}. Run the generation script first.")
        return None
    except Exception as e:
        st.error(f"Error loading observation data: {e}")
        return None