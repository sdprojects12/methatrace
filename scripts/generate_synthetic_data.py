import os
import json
import random
import datetime
import csv

print("Generating synthetic data for MethaTrace prototype...")

MIN_LAT, MAX_LAT = 18.70, 18.80
MIN_LON, MAX_LON = 73.80, 73.90

# Generate Pipelines (GeoJSON)
num_pipelines = 25
features = []

for i in range(num_pipelines):
    start_lon = random.uniform(MIN_LON, MAX_LON)
    start_lat = random.uniform(MIN_LAT, MAX_LAT)
    end_lon = max(MIN_LON, min(MAX_LON, start_lon + random.uniform(-0.02, 0.02)))
    end_lat = max(MIN_LAT, min(MAX_LAT, start_lat + random.uniform(-0.02, 0.02)))
    
    feature = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[start_lon, start_lat], [end_lon, end_lat]]
        },
        "properties": {
            "pipeline_id": f"PL-CHKN-{i:03d}",
            "start_coords": f"({start_lat:.4f}, {start_lon:.4f})",
            "end_coords": f"({end_lat:.4f}, {end_lon:.4f})",
            "installation_year": random.randint(2000, 2023),
            "material": random.choice(['Steel', 'HDPE', 'Cast Iron']),
            "status": random.choice(['Active', 'Active', 'Active', 'Maintenance'])
        }
    }
    features.append(feature)

geojson_data = {
    "type": "FeatureCollection",
    "features": features
}

os.makedirs('data', exist_ok=True)
pipelines_path = os.path.join('data', 'chakan_pipelines.geojson')
with open(pipelines_path, 'w') as f:
    json.dump(geojson_data, f, indent=2)
print(f"-> Created {pipelines_path} with {num_pipelines} synthetic pipelines.")

# Generate Methane Observations (CSV)
num_obs = 150
observations = []
end_time = datetime.datetime.now()

for i in range(num_obs):
    lon = random.uniform(MIN_LON, MAX_LON)
    lat = random.uniform(MIN_LAT, MAX_LAT)
    
    source = random.choice(['Pipeline Leak', 'Industrial Vent', 'Background', 'Background'])
    if source == 'Background':
        ppm = random.uniform(1.8, 2.5)
    elif source == 'Industrial Vent':
        ppm = random.uniform(3.0, 15.0)
    else:
        ppm = random.uniform(5.0, 45.0)
        
    is_anomaly = bool(ppm > 5.0)
    obs_time = end_time - datetime.timedelta(days=random.uniform(0, 30), hours=random.uniform(0, 24))
    
    observations.append({
        'observation_id': f"OBS-{i:04d}",
        'timestamp': obs_time.strftime("%Y-%m-%d %H:%M:%S"),
        'latitude': round(lat, 6),
        'longitude': round(lon, 6),
        'methane_concentration_ppm': round(ppm, 2),
        'source_label': source,
        'is_anomaly': is_anomaly
    })

obs_path = os.path.join('data', 'methane_observations.csv')
with open(obs_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=observations[0].keys())
    writer.writeheader()
    writer.writerows(observations)

print(f"-> Created {obs_path} with {num_obs} synthetic observations.")
print("Synthetic data generation complete. Note: All data is strictly simulated for the college prototype.")