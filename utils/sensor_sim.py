import random

def generate_sensor_readings(pipeline_id: str, trigger_anomaly: bool = False) -> dict:
    """
    Simulates real-time IoT pressure (Bar) and flow (m3/h) readings for a pipeline.
    """
    base_pressure = random.uniform(45.0, 52.0) 
    base_flow = random.uniform(100.0, 120.0)   
    
    if trigger_anomaly:
        pressure = base_pressure * 0.4
        flow = base_flow * 1.8
        status = "CRITICAL: RAPID PRESSURE DROP DETECTED"
    else:
        pressure = base_pressure
        flow = base_flow
        status = "NORMAL"
        
    return {
        "pipeline_id": pipeline_id,
        "pressure_bar": round(pressure, 2),
        "flow_rate_m3h": round(flow, 2),
        "sensor_status": status
    }