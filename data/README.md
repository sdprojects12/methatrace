# MethaTrace - Synthetic Data Module

**Disclaimer:** All data in this directory is strictly synthetic and simulated for the MethaTrace college prototype. It does not represent real-world methane emissions or actual pipeline infrastructure in the Chakan industrial area.

## Data Dictionary

### 1. chakan_pipelines.geojson
Contains synthetic pipeline segments geographically bounded to the Chakan industrial area.
* `pipeline_id`: Unique identifier for the pipeline segment (e.g., PL-CHKN-001).
* `start_coords`: Latitude and longitude of the starting point.
* `end_coords`: Latitude and longitude of the ending point.
* `installation_year`: Simulated year of installation (2000-2023).
* `material`: Construction material (Steel, HDPE, Cast Iron).
* `status`: Current operational status (Active, Maintenance).

### 2. methane_observations.csv
Contains simulated methane readings near the pipeline infrastructure.
* `observation_id`: Unique identifier for the reading.
* `timestamp`: Date and time of the observation.
* `latitude`: Y-coordinate of the reading.
* `longitude`: X-coordinate of the reading.
* `methane_concentration_ppm`: Simulated methane concentration in parts per million (ppm).
* `source_label`: Categorized source (Pipeline Leak, Industrial Vent, Background).
* `is_anomaly`: Boolean flag indicating if the concentration exceeds the baseline threshold (> 5.0 ppm).