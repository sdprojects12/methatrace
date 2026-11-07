
import random

# Simulation factors
ANOMALY_PRESSURE_FACTOR = 0.4
ANOMALY_FLOW_FACTOR = 1.8


def generate_sensor_readings(
    pipeline_id: str,
    trigger_anomaly: bool = False,
    seed: int = None,
    base_pressure_bar: float = None,
) -> dict:
    """
    Generate synthetic IoT pressure and flow readings.

    Supports reproducible readings, pipeline-rated pressure,
    and simulated anomaly scenarios.
    """

    rng = random.Random(seed)

    # Generate the normal baseline
    if base_pressure_bar is not None:
        baseline_pressure = rng.uniform(
            base_pressure_bar * 0.95,
            base_pressure_bar * 1.05
        )
    else:
        baseline_pressure = rng.uniform(45.0, 52.0)

    baseline_flow = rng.uniform(100.0, 120.0)

    # Apply anomaly factors to the same baseline
    if trigger_anomaly:
        pressure = baseline_pressure * ANOMALY_PRESSURE_FACTOR
        flow = baseline_flow * ANOMALY_FLOW_FACTOR
        status = "CRITICAL: RAPID PRESSURE DROP DETECTED"
    else:
        pressure = baseline_pressure
        flow = baseline_flow
        status = "NORMAL"

    return {
        "pipeline_id": pipeline_id,
        "pressure_bar": round(pressure, 2),
        "flow_rate_m3h": round(flow, 2),
        "baseline_pressure_bar": round(baseline_pressure, 2),
        "baseline_flow_rate_m3h": round(baseline_flow, 2),
        "pressure_delta_bar": round(pressure - baseline_pressure, 2),
        "flow_delta_m3h": round(flow - baseline_flow, 2),
        "sensor_status": status,
        "is_anomaly": trigger_anomaly,
        "synthetic": True,
    }
