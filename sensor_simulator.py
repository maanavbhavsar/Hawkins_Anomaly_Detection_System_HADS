"""
Sensor Simulator Module
=======================
Generates random lab sensor data every 5 seconds.
Simulates anomalies ~10% of the time for testing alerting systems.

Sensors included:
- Temperature (°C)
- Gas concentration (ppm)
- Vibration (mm/s)
- CPU usage (%)

Future Datadog Integration:
--------------------------
To send metrics to Datadog, you can use the datadog-api-client library:
    from datadog_api_client import ApiClient, Configuration
    from datadog_api_client.v2.api.metrics_api import MetricsApi

Each sensor reading can be sent as a custom metric:
    - lab.sensor.temperature
    - lab.sensor.gas
    - lab.sensor.vibration
    - lab.sensor.cpu_usage

Tags can include: sensor_id, location, anomaly_status
"""

import random
import time
from datetime import datetime, timezone


# Normal operating ranges for each sensor
SENSOR_CONFIG = {
    "temperature": {
        "unit": "°C",
        "normal_min": 18.0,
        "normal_max": 28.0,
        "anomaly_min": -10.0,
        "anomaly_max": 60.0,
    },
    "gas": {
        "unit": "ppm",
        "normal_min": 0.0,
        "normal_max": 50.0,
        "anomaly_min": 100.0,
        "anomaly_max": 500.0,
    },
    "vibration": {
        "unit": "mm/s",
        "normal_min": 0.0,
        "normal_max": 2.5,
        "anomaly_min": 8.0,
        "anomaly_max": 20.0,
    },
    "cpu_usage": {
        "unit": "%",
        "normal_min": 5.0,
        "normal_max": 70.0,
        "anomaly_min": 95.0,
        "anomaly_max": 100.0,
    },
}

# Probability of generating an anomaly per sensor (~1 anomaly every 30 sec at 5s cycle)
ANOMALY_PROBABILITY = 0.04


def generate_sensor_value(sensor_name: str) -> tuple[float, bool]:
    """
    Generate a sensor reading, with ANOMALY_PROBABILITY chance of being anomalous.
    
    Args:
        sensor_name: Name of the sensor (must exist in SENSOR_CONFIG)
    
    Returns:
        Tuple of (value, is_anomaly)
    """
    config = SENSOR_CONFIG[sensor_name]
    is_anomaly = random.random() < ANOMALY_PROBABILITY
    
    if is_anomaly:
        # Generate anomalous value (outside normal range)
        value = random.uniform(config["anomaly_min"], config["anomaly_max"])
    else:
        # Generate normal value (within expected range)
        value = random.uniform(config["normal_min"], config["normal_max"])
    
    return round(value, 2), is_anomaly


def generate_sensor_data(sensor_id: str = "LAB-001", location: str = "main_lab") -> dict:
    """
    Generate a complete sensor data reading with all sensors.
    
    Args:
        sensor_id: Unique identifier for the sensor station
        location: Physical location of the sensors
    
    Returns:
        Dictionary containing all sensor readings and metadata
        
        Example output:
        {
            "timestamp": "2026-02-20T15:30:45.123456+00:00",
            "sensor_id": "LAB-001",
            "location": "main_lab",
            "readings": {
                "temperature": {"value": 23.5, "unit": "°C", "is_anomaly": False},
                "gas": {"value": 12.3, "unit": "ppm", "is_anomaly": False},
                "vibration": {"value": 1.2, "unit": "mm/s", "is_anomaly": False},
                "cpu_usage": {"value": 45.6, "unit": "%", "is_anomaly": False}
            },
            "has_anomaly": False
        }
    """
    readings = {}
    has_any_anomaly = False
    
    for sensor_name, config in SENSOR_CONFIG.items():
        value, is_anomaly = generate_sensor_value(sensor_name)
        readings[sensor_name] = {
            "value": value,
            "unit": config["unit"],
            "is_anomaly": is_anomaly,
        }
        if is_anomaly:
            has_any_anomaly = True
    
    # Build the complete data dictionary
    # Datadog Note: Use ISO format timestamp for proper time series alignment
    sensor_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sensor_id": sensor_id,
        "location": location,
        "readings": readings,
        "has_anomaly": has_any_anomaly,  # Quick flag for alerting
    }
    
    return sensor_data


def run_simulator(
    interval_seconds: float = 5.0,
    sensor_id: str = "LAB-001",
    location: str = "main_lab",
    max_iterations: int | None = None,
) -> None:
    """
    Run the sensor simulator in a continuous loop.
    
    Args:
        interval_seconds: Time between readings (default: 5 seconds)
        sensor_id: Unique identifier for the sensor station
        location: Physical location of the sensors
        max_iterations: Optional limit on number of readings (None = infinite)
    
    Datadog Integration Point:
    -------------------------
    This is where you would add the Datadog metrics submission:
    
        from datadog_api_client.v2.model.metric_intake_type import MetricIntakeType
        from datadog_api_client.v2.model.metric_series import MetricSeries
        
        # Submit each reading as a metric
        for sensor_name, reading in data["readings"].items():
            series = MetricSeries(
                metric=f"lab.sensor.{sensor_name}",
                type=MetricIntakeType.GAUGE,
                points=[...],
                tags=[
                    f"sensor_id:{data['sensor_id']}",
                    f"location:{data['location']}",
                    f"anomaly:{reading['is_anomaly']}"
                ]
            )
    """
    print(f"Starting sensor simulator (interval: {interval_seconds}s)")
    print(f"Sensor ID: {sensor_id}, Location: {location}")
    print(f"Anomaly probability: {ANOMALY_PROBABILITY * 100}%")
    print("-" * 60)
    
    iteration = 0
    try:
        while max_iterations is None or iteration < max_iterations:
            data = generate_sensor_data(sensor_id=sensor_id, location=location)
            
            # Display the reading
            anomaly_indicator = " [ANOMALY DETECTED]" if data["has_anomaly"] else ""
            print(f"\n[{data['timestamp']}]{anomaly_indicator}")
            
            for sensor_name, reading in data["readings"].items():
                status = "⚠️ ANOMALY" if reading["is_anomaly"] else "✓ Normal"
                print(f"  {sensor_name}: {reading['value']} {reading['unit']} ({status})")
            
            # Datadog Note: This is where you would call your metrics submission function
            # send_to_datadog(data)
            
            iteration += 1
            
            # Wait for next reading (unless we've hit our limit)
            if max_iterations is None or iteration < max_iterations:
                time.sleep(interval_seconds)
                
    except KeyboardInterrupt:
        print("\n\nSimulator stopped by user.")


# For importing as a module
def get_single_reading(sensor_id: str = "LAB-001", location: str = "main_lab") -> dict:
    """
    Convenience function to get a single sensor reading.
    Useful for one-off data collection or testing.
    
    Args:
        sensor_id: Unique identifier for the sensor station
        location: Physical location of the sensors
    
    Returns:
        Dictionary with sensor data (same format as generate_sensor_data)
    """
    return generate_sensor_data(sensor_id=sensor_id, location=location)


if __name__ == "__main__":
    # Run the simulator when executed directly
    # Ctrl+C to stop
    run_simulator(interval_seconds=5.0)
