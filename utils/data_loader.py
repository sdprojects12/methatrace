import os
import pandas as pd
import geopandas as gpd

# Resolve absolute paths relative to this utility script
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')

PIPELINES_FILE = os.path.join(DATA_DIR, 'chakan_pipelines_simulated.geojson')
OBSERVATIONS_FILE = os.path.join(DATA_DIR, 'methane_observations.csv')

PIPELINE_REQUIRED_COLUMNS = ("pipeline_id", "status")
OBSERVATION_REQUIRED_COLUMNS = ("timestamp", "latitude", "longitude", "methane_concentration_ppm")


class DataLoadError(Exception):
    """Raised when a dataset is missing, unreadable, empty or lacks required columns."""


def read_pipelines(path: str = None) -> gpd.GeoDataFrame:
    """
    Reads and validates the synthetic pipeline GeoJSON.
    Pure function; raises DataLoadError with a readable message.
    """
    path = path or PIPELINES_FILE
    if not os.path.exists(path):
        raise DataLoadError(
            f"Pipeline data file not found at {path}. Run scripts/generate_synthetic_data.py first."
        )
    try:
        gdf = gpd.read_file(path)
    except Exception as e:
        raise DataLoadError(f"Error loading pipeline data: {e}") from e
    missing = [c for c in PIPELINE_REQUIRED_COLUMNS if c not in gdf.columns]
    if missing:
        raise DataLoadError(f"Pipeline data is missing required columns: {', '.join(missing)}.")
    if gdf.empty:
        raise DataLoadError("Pipeline dataset is empty.")
    return gdf


def read_observations(path: str = None) -> pd.DataFrame:
    """
    Reads and validates the synthetic methane observation CSV.
    Pure function; raises DataLoadError with a readable message.
    """
    path = path or OBSERVATIONS_FILE
    if not os.path.exists(path):
        raise DataLoadError(
            f"Observation data file not found at {path}. Run scripts/generate_synthetic_data.py first."
        )
    try:
        obs_df = pd.read_csv(path)
    except Exception as e:
        raise DataLoadError(f"Error loading observation data: {e}") from e
    missing = [c for c in OBSERVATION_REQUIRED_COLUMNS if c not in obs_df.columns]
    if missing:
        raise DataLoadError(f"Observation data is missing required columns: {', '.join(missing)}.")
    try:
        obs_df['timestamp'] = pd.to_datetime(obs_df['timestamp'])
    except Exception as e:
        raise DataLoadError(f"Observation timestamps could not be parsed: {e}") from e
    if obs_df.empty:
        raise DataLoadError("Observation dataset is empty.")
    return obs_df


def load_pipelines():
    """
    Load synthetic pipeline GeoJSON data for the Chakan area.

    Raises DataLoadError when the dataset is missing or invalid. Callers choose
    their own caching and error-reporting behavior.
    """
    return read_pipelines()

def load_observations():
    """
    Load synthetic methane observations with parsed timestamps.

    Raises DataLoadError when the dataset is missing or invalid. Callers choose
    their own caching and error-reporting behavior.
    """
    return read_observations()
