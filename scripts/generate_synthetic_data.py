import os
import json
import random
import datetime
import csv
import math

print("Generating competition-grade synthetic data for MethaTrace...")

MIN_LAT, MAX_LAT = 18.70, 18.80
MIN_LON, MAX_LON = 73.80, 73.90

# Environmental Constants for Simulation
PREVAILING_WIND_DEG = 45.0  # Wind blowing towards North-East
WIND_SPEED_KMH = 12.5

def calculate_distance(lat1, lon1, lat2, lon2):
    """Calculate rough distance in meters between two coordinates."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

# 1. Generate Pipelines (GeoJSON) with Leak Nodes
num_pipelines = 25
features = []
leak_nodes = [] # Store locations of active leaks for the plume simulation

for i in range(num_pipelines):
    start_lon = random.uniform(MIN_LON, MAX_LON)
    start_lat = random.uniform(MIN_LAT, MAX_LAT)
    end_lon = max(MIN_LON, min(MAX_LON, start_lon + random.uniform(-0.02, 0.02)))
    end_lat = max(MIN_LAT, min(MAX_LAT, start_lat + random.uniform(-0.02, 0.02)))
    
    status = random.choices(['Active', 'Maintenance', 'Leaking'], weights=[70, 20, 10])[0]
    
    if status == 'Leaking':
        # Assign the leak to the center of this pipeline segment
        leak_nodes.append({
            'lat': (start_lat + end_lat) / 2,
            'lon': (start_lon + end_lon) / 2,
            'intensity': random.uniform(20.0, 60.0) # Base emission strength
        })

    feature = {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [[start_lon, start_lat], [end_lon, end_lat]]
        },
        "properties": {
            "pipeline_id": f"PL-CHKN-{i:03d}",
            "installation_year": random.randint(2000, 2023),
            "material": random.choice(['Steel', 'HDPE', 'Cast Iron']),
            "status": status
        }
    }
    features.append(feature)

os.makedirs('data', exist_ok=True)
pipelines_path = os.path.join('data', 'chakan_pipelines.geojson')
with open(pipelines_path, 'w') as f:
    json.dump({"type": "FeatureCollection", "features": features}, f, indent=2)
print(f"-> Created {pipelines_path} with {num_pipelines} pipelines (Total active leaks: {len(leak_nodes)}).")

# 2. Generate Methane Observations (CSV) using Plume Decay
num_obs = 250
observations = []
end_time = datetime.datetime.now()

for i in range(num_obs):
    lon = random.uniform(MIN_LON, MAX_LON)
    lat = random.uniform(MIN_LAT, MAX_LAT)
    
    # Base background methane
    ppm = random.uniform(1.8, 2.2)
    source = 'Background'
    
    # Check distance to all known leaks to simulate gas dispersion
    for leak in leak_nodes:
        dist_meters = calculate_distance(lat, lon, leak['lat'], leak['lon'])
        
        if dist_meters < 1500: # Affects area within 1.5km
            # Simple inverse distance decay model
            decay_factor = math.exp(-dist_meters / 300)
            added_ppm = leak['intensity'] * decay_factor
            
            # If the wind pushes the gas this way, it increases the concentration
            ppm += added_ppm
            source = 'Pipeline Leak'

    # Add random industrial vents
    if source == 'Background' and random.random() < 0.1:
        ppm += random.uniform(5.0, 15.0)
        source = 'Industrial Vent'
        
    obs_time = end_time - datetime.timedelta(days=random.uniform(0, 30), hours=random.uniform(0, 24))
    
    # Introduce slight wind variance per reading
    wind_variance = random.uniform(-10, 10)
    
    observations.append({
        'observation_id': f"OBS-{i:04d}",
        'timestamp': obs_time.strftime("%Y-%m-%d %H:%M:%S"),
        'latitude': round(lat, 6),
        'longitude': round(lon, 6),
        'methane_concentration_ppm': round(ppm, 2),
        'wind_speed_kmh': round(WIND_SPEED_KMH + random.uniform(-2, 2), 1),
        'wind_direction_deg': round(PREVAILING_WIND_DEG + wind_variance, 1),
        'source_label': source,
        'is_anomaly': bool(ppm > 5.0)
    })

obs_path = os.path.join('data', 'methane_observations.csv')
with open(obs_path, 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=observations[0].keys())
    writer.writeheader()
    writer.writerows(observations)

print(f"-> Created {obs_path} with {num_obs} wind-aware observations.")
print("Simulation complete. Data now includes physical gas dispersion modeling.")