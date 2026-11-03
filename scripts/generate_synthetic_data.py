import os
import json
import random
import datetime
import csv
import math

print("Initializing Sentinel-5P & SCADA Simulation for Chakan MIDC...")

HUB = {"lon": 73.830, "lat": 18.750}
CHAKAN_ZONES = [
    {"name": "Tata Motors Sector", "lon": 73.818, "lat": 18.748},
    {"name": "Mahindra Plant Area", "lon": 73.791, "lat": 18.790},
    {"name": "MIDC Phase 2", "lon": 73.800, "lat": 18.775},
    {"name": "Bajaj Auto Corridor", "lon": 73.820, "lat": 18.715}
]

features = []
leak_nodes = []
pipeline_id_counter = 1
current_year = datetime.datetime.now().year

# 1. Build the SCADA Pipeline Network
for zone in CHAKAN_ZONES:
    features.append({
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": [[HUB["lon"], HUB["lat"]], [zone["lon"], zone["lat"]]]},
        "properties": {
            "pipeline_id": f"TRUNK-{pipeline_id_counter:03d}",
            "type": "Main Trunk",
            "status": "Active",
            "material": "High-Pressure Steel",
            "pressure_bar": round(random.uniform(60, 80), 1),
            "depth_m": round(random.uniform(2.5, 4.0), 1),
            "installed": random.randint(1995, 2010)
        }
    })
    pipeline_id_counter += 1

    grid_size = 4
    step = 0.005
    start_lon, start_lat = zone["lon"] - (step*2), zone["lat"] - (step*2)

    for i in range(grid_size):
        for j in range(grid_size):
            lon, lat = start_lon + (i * step), start_lat + (j * step)
            
            # Distribution Lines with Metadata
            for is_vertical in [False, True]:
                end_lon = lon if is_vertical else lon + step
                end_lat = lat + step if is_vertical else lat
                
                status = random.choices(['Active', 'Maintenance', 'Leaking'], weights=[88, 10, 2])[0]
                if status == 'Leaking': 
                    leak_nodes.append({"lon": (lon+end_lon)/2, "lat": (lat+end_lat)/2, "intensity": random.uniform(30, 70)})
                
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": [[lon, lat], [end_lon, end_lat]]},
                    "properties": {
                        "pipeline_id": f"DIST-{pipeline_id_counter:04d}", 
                        "type": "Distribution", 
                        "status": status, 
                        "material": "HDPE",
                        "pressure_bar": round(random.uniform(15, 30), 1),
                        "depth_m": round(random.uniform(1.0, 2.0), 1),
                        "installed": random.randint(2015, current_year)
                    }
                })
                pipeline_id_counter += 1

os.makedirs('data', exist_ok=True)
with open('data/chakan_pipelines.geojson', 'w') as f:
    json.dump({"type": "FeatureCollection", "features": features}, f, indent=2)

print(f"-> Generated {len(features)} SCADA pipelines (Active leaks: {len(leak_nodes)}).")

# 2. Generate Methane Observations with Directional Wind Plumes
PREVAILING_WIND_DEG = 45.0  # Wind blowing Northeast
WIND_SPEED_KMH = 15.0
WIND_RAD = math.radians(PREVAILING_WIND_DEG)
num_obs = 600
observations = []
end_time = datetime.datetime.now()

def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    dphi, dlambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(math.radians(lat1))*math.cos(math.radians(lat2))*math.sin(dlambda/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

for i in range(num_obs):
    # Base coordinate
    target_zone = random.choice(CHAKAN_ZONES)
    lon = target_zone["lon"] + random.uniform(-0.04, 0.04)
    lat = target_zone["lat"] + random.uniform(-0.04, 0.04)
    
    ppm = random.uniform(1.85, 2.10) 
    source = 'Background'
    
    for leak in leak_nodes:
        # Calculate raw distance
        dist_meters = calculate_distance(lat, lon, leak['lat'], leak['lon'])
        
        # Calculate angle from leak to observation
        angle_to_obs = math.atan2(lon - leak['lon'], lat - leak['lat'])
        
        # Plume physics: Gas concentration is highest downwind
        angle_diff = abs(angle_to_obs - WIND_RAD)
        if angle_diff > math.pi: angle_diff = (2 * math.pi) - angle_diff
        
        # If observation is downwind (angle_diff is small), gas travels further
        wind_factor = math.exp(-angle_diff * 2) 
        effective_distance = dist_meters / (0.5 + (wind_factor * (WIND_SPEED_KMH / 5)))

        if effective_distance < 800:
            added_ppm = leak['intensity'] * math.exp(-effective_distance / 150)
            if added_ppm > 2.0:
                ppm += added_ppm
                source = 'Pipeline Leak'

    observations.append({
        'observation_id': f"OBS-{i:04d}",
        'timestamp': (end_time - datetime.timedelta(hours=random.uniform(0, 24))).strftime("%Y-%m-%d %H:%M:%S"),
        'latitude': round(lat, 6),
        'longitude': round(lon, 6),
        'methane_concentration_ppm': round(ppm, 2),
        'wind_speed_kmh': round(WIND_SPEED_KMH + random.uniform(-3, 3), 1),
        'wind_direction_deg': round(PREVAILING_WIND_DEG + random.uniform(-5, 5), 1),
        'source_label': source,
        'is_anomaly': bool(ppm > 7.0)
    })

with open('data/methane_observations.csv', 'w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=observations[0].keys())
    writer.writeheader()
    writer.writerows(observations)

print("-> Plume physics applied. Data generation complete.")