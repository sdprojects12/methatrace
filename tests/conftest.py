import pandas as pd
import geopandas as gpd
import pytest
from shapely.geometry import LineString


@pytest.fixture
def pipelines():
    """Two short synthetic segments near Chakan (lon, lat order in geometry)."""
    gdf = gpd.GeoDataFrame(
        {
            "pipeline_id": ["P-A", "P-B"],
            "type": ["Main Trunk", "Distribution"],
            "status": ["Active", "Leaking"],
            "material": ["Steel", "HDPE"],
            "pressure_bar": [70.0, 8.0],
            "depth_m": [2.0, 1.2],
            "installed": [1998, 2015],
        },
        geometry=[LineString([(73.800, 18.750), (73.810, 18.750)]), LineString([(73.900, 18.800), (73.910, 18.800)])],
        crs="EPSG:4326",
    )
    return gdf


@pytest.fixture
def observations():
    return pd.DataFrame(
        {
            "observation_id": ["O1", "O2", "O3", "O4"],
            "timestamp": pd.to_datetime(["2026-10-29 10:00", "2026-10-29 11:00", "2026-10-29 12:00", "2026-10-29 13:00"]),
            "latitude": [18.7501, 18.7502, 18.8001, 19.5],   # O1,O2 ~11-22 m from P-A; O3 ~11 m from P-B; O4 far away
            "longitude": [73.805, 73.806, 73.905, 73.805],
            "methane_concentration_ppm": [2.0, 6.5, 4.0, 2.0],
            "wind_speed_kmh": [10.0, 10.0, 10.0, 10.0],
            "wind_direction_deg": [45.0] * 4,
            "source_label": ["Background", "Pipeline Leak", "Pipeline Leak", "Background"],
            "is_anomaly": [False, False, False, False],
        }
    )
