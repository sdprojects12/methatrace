import os
import pytest
import pandas as pd
import geopandas as gpd
from utils.data_loader import load_pipelines, load_observations, PIPELINES_FILE, OBSERVATIONS_FILE

def test_files_exist():
    assert os.path.exists(PIPELINES_FILE), "Pipeline GeoJSON file is missing"
    assert os.path.exists(OBSERVATIONS_FILE), "Observations CSV file is missing"

def test_load_pipelines():
    gdf = load_pipelines()
    assert gdf is not None, "Failed to load pipelines"
    assert isinstance(gdf, gpd.GeoDataFrame), "Expected a GeoDataFrame"
    assert not gdf.empty, "Pipeline dataset is empty"
    assert "pipeline_id" in gdf.columns, "Missing pipeline_id column"
    assert "material" in gdf.columns, "Missing material column"

def test_load_observations():
    df = load_observations()
    assert df is not None, "Failed to load observations"
    assert isinstance(df, pd.DataFrame), "Expected a DataFrame"
    assert not df.empty, "Observation dataset is empty"
    assert "methane_concentration_ppm" in df.columns, "Missing methane concentration column"
    assert "timestamp" in df.columns, "Missing timestamp column"
    assert pd.api.types.is_datetime64_any_dtype(df['timestamp']), "Timestamp column not parsed as datetime"