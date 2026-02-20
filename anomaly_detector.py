"""
Anomaly Detector Module
=======================
Detects anomalies in lab sensor data using threshold-based and z-score methods.

Input: Sensor data dictionary (from sensor_simulator.py)
Output: Detection result with anomaly flag and triggered sensor summary

Detection Methods:
-----------------
1. Threshold-based: Simple min/max bounds checking
2. Z-score: Statistical deviation from rolling mean (requires history)

AWS Bedrock Integration:
-----------------------
You can enhance anomaly detection with AWS Bedrock's foundation models:

    import boto3
    
    bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
    
    # Use Claude or other models to analyze anomaly patterns
    response = bedrock.invoke_model(
        modelId='anthropic.claude-3-sonnet-20240229-v1:0',
        body=json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "messages": [{
                "role": "user",
                "content": f"Analyze this sensor anomaly: {anomaly_summary}"
            }],
            "max_tokens": 500
        })
    )
    
    # Parse response for root cause analysis or recommended actions

Datadog Integration:
-------------------
Send anomaly events and metrics to Datadog:

    from datadog_api_client.v1.api.events_api import EventsApi
    from datadog_api_client.v1.model.event_create_request import EventCreateRequest
    
    # Create an event when anomaly is detected
    event = EventCreateRequest(
        title="Lab Sensor Anomaly Detected",
        text=f"Sensors triggered: {triggered_sensors}",
        alert_type="warning",
        tags=["env:lab", "source:anomaly_detector"]
    )
    
    # Or use custom metrics for anomaly tracking
    # lab.anomaly.count (counter)
    # lab.anomaly.zscore (gauge per sensor)
"""

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any


# Threshold configuration for each sensor type
# Values outside these ranges are considered anomalous
THRESHOLDS = {
    "temperature": {"min": 15.0, "max": 32.0, "unit": "°C"},
    "gas": {"min": 0.0, "max": 75.0, "unit": "ppm"},
    "vibration": {"min": 0.0, "max": 4.0, "unit": "mm/s"},
    "cpu_usage": {"min": 0.0, "max": 85.0, "unit": "%"},
}

# Z-score threshold: values beyond this many standard deviations are anomalous
Z_SCORE_THRESHOLD = 2.5

# Minimum samples needed before z-score detection is reliable
MIN_SAMPLES_FOR_ZSCORE = 10


@dataclass
class SensorHistory:
    """
    Maintains rolling statistics for z-score calculation.
    Uses Welford's online algorithm for numerically stable variance.
    """
    max_samples: int = 100
    values: deque = field(default_factory=lambda: deque(maxlen=100))
    count: int = 0
    mean: float = 0.0
    m2: float = 0.0  # Sum of squared differences from mean
    
    def add_value(self, value: float) -> None:
        """Add a new value and update running statistics."""
        # If buffer is full, we need to recalculate from scratch
        # (Welford's algorithm doesn't support removal)
        if len(self.values) >= self.max_samples:
            self.values.append(value)
            self._recalculate_stats()
        else:
            self.values.append(value)
            self.count += 1
            delta = value - self.mean
            self.mean += delta / self.count
            delta2 = value - self.mean
            self.m2 += delta * delta2
    
    def _recalculate_stats(self) -> None:
        """Recalculate statistics from the current buffer."""
        if not self.values:
            self.count = 0
            self.mean = 0.0
            self.m2 = 0.0
            return
        
        self.count = len(self.values)
        self.mean = sum(self.values) / self.count
        self.m2 = sum((x - self.mean) ** 2 for x in self.values)
    
    @property
    def variance(self) -> float:
        """Population variance of the stored values."""
        if self.count < 2:
            return 0.0
        return self.m2 / self.count
    
    @property
    def std_dev(self) -> float:
        """Population standard deviation."""
        return math.sqrt(self.variance)
    
    def get_zscore(self, value: float) -> float | None:
        """
        Calculate z-score for a given value.
        Returns None if insufficient data for reliable calculation.
        """
        if self.count < MIN_SAMPLES_FOR_ZSCORE:
            return None
        if self.std_dev == 0:
            return 0.0 if value == self.mean else None
        return (value - self.mean) / self.std_dev


class AnomalyDetector:
    """
    Detects anomalies in sensor data using multiple detection methods.
    
    Usage:
        detector = AnomalyDetector()
        result = detector.analyze(sensor_data)
        
        if result["anomaly_detected"]:
            print(f"Anomalies found: {result['triggered_sensors']}")
    
    AWS Bedrock Enhancement:
    -----------------------
    After detecting anomalies, you can use Bedrock for intelligent analysis:
    
        if result["anomaly_detected"]:
            # Send to Bedrock for root cause analysis
            analysis = bedrock_analyze_anomaly(result)
            result["ai_analysis"] = analysis
            result["recommended_actions"] = analysis.get("actions", [])
    """
    
    def __init__(
        self,
        thresholds: dict[str, dict] | None = None,
        z_score_threshold: float = Z_SCORE_THRESHOLD,
        use_zscore: bool = True,
        history_size: int = 100,
    ):
        """
        Initialize the anomaly detector.
        
        Args:
            thresholds: Custom threshold config (uses defaults if None)
            z_score_threshold: Number of std devs for z-score anomaly
            use_zscore: Enable z-score detection (requires history)
            history_size: Number of samples to keep for z-score calculation
        """
        self.thresholds = thresholds or THRESHOLDS
        self.z_score_threshold = z_score_threshold
        self.use_zscore = use_zscore
        self.history_size = history_size
        
        # Maintain per-sensor history for z-score calculation
        self.sensor_history: dict[str, SensorHistory] = {}
    
    def _get_or_create_history(self, sensor_name: str) -> SensorHistory:
        """Get or create history tracker for a sensor."""
        if sensor_name not in self.sensor_history:
            self.sensor_history[sensor_name] = SensorHistory(max_samples=self.history_size)
        return self.sensor_history[sensor_name]
    
    def check_threshold(self, sensor_name: str, value: float) -> dict[str, Any]:
        """
        Check if a value exceeds threshold bounds.
        
        Returns:
            Dictionary with threshold check results
        """
        if sensor_name not in self.thresholds:
            return {"checked": False, "reason": "no_threshold_config"}
        
        config = self.thresholds[sensor_name]
        min_val = config["min"]
        max_val = config["max"]
        
        is_anomaly = value < min_val or value > max_val
        
        return {
            "checked": True,
            "is_anomaly": is_anomaly,
            "value": value,
            "min_threshold": min_val,
            "max_threshold": max_val,
            "violation": "below_min" if value < min_val else ("above_max" if value > max_val else None),
        }
    
    def check_zscore(self, sensor_name: str, value: float) -> dict[str, Any]:
        """
        Check if a value deviates significantly from historical mean.
        
        Returns:
            Dictionary with z-score check results
        """
        history = self._get_or_create_history(sensor_name)
        zscore = history.get_zscore(value)
        
        if zscore is None:
            return {
                "checked": False,
                "reason": "insufficient_history",
                "samples_needed": MIN_SAMPLES_FOR_ZSCORE,
                "samples_collected": history.count,
            }
        
        is_anomaly = abs(zscore) > self.z_score_threshold
        
        return {
            "checked": True,
            "is_anomaly": is_anomaly,
            "zscore": round(zscore, 3),
            "threshold": self.z_score_threshold,
            "mean": round(history.mean, 3),
            "std_dev": round(history.std_dev, 3),
        }
    
    def analyze(self, sensor_data: dict) -> dict[str, Any]:
        """
        Analyze sensor data for anomalies.
        
        Args:
            sensor_data: Dictionary from sensor_simulator.generate_sensor_data()
                Expected format:
                {
                    "timestamp": "...",
                    "sensor_id": "...",
                    "readings": {
                        "temperature": {"value": 23.5, ...},
                        ...
                    }
                }
        
        Returns:
            Detection result dictionary:
            {
                "anomaly_detected": bool,
                "triggered_sensors": ["sensor1", "sensor2"],
                "summary": {
                    "sensor1": {
                        "value": float,
                        "threshold_result": {...},
                        "zscore_result": {...},
                        "reasons": ["above_max", "zscore_exceeded"]
                    }
                },
                "metadata": {
                    "timestamp": "...",
                    "sensor_id": "...",
                    "detection_methods": ["threshold", "zscore"]
                }
            }
            
        Datadog Integration Point:
        -------------------------
        After calling analyze(), send results to Datadog:
        
            result = detector.analyze(sensor_data)
            
            # Send anomaly count metric
            send_metric("lab.anomaly.count", 
                        value=len(result["triggered_sensors"]),
                        tags=[f"sensor_id:{sensor_data['sensor_id']}"])
            
            # Create event if anomaly detected
            if result["anomaly_detected"]:
                create_event(
                    title="Anomaly Detected",
                    text=json.dumps(result["summary"]),
                    alert_type="warning"
                )
        """
        readings = sensor_data.get("readings", {})
        triggered_sensors = []
        summary = {}
        
        for sensor_name, reading in readings.items():
            value = reading.get("value")
            if value is None:
                continue
            
            sensor_result = {
                "value": value,
                "unit": reading.get("unit", ""),
                "reasons": [],
            }
            
            # Check threshold bounds
            threshold_result = self.check_threshold(sensor_name, value)
            sensor_result["threshold_result"] = threshold_result
            
            if threshold_result.get("is_anomaly"):
                sensor_result["reasons"].append(f"threshold_{threshold_result['violation']}")
            
            # Check z-score (if enabled)
            if self.use_zscore:
                zscore_result = self.check_zscore(sensor_name, value)
                sensor_result["zscore_result"] = zscore_result
                
                if zscore_result.get("is_anomaly"):
                    sensor_result["reasons"].append("zscore_exceeded")
                
                # Update history with this value (after checking)
                history = self._get_or_create_history(sensor_name)
                history.add_value(value)
            
            # Mark sensor as triggered if any anomaly detected
            if sensor_result["reasons"]:
                triggered_sensors.append(sensor_name)
                summary[sensor_name] = sensor_result
        
        # Build final result
        # AWS Bedrock Note: This result can be sent to Bedrock for AI-powered analysis
        result = {
            "anomaly_detected": len(triggered_sensors) > 0,
            "triggered_sensors": triggered_sensors,
            "summary": summary,
            "metadata": {
                "timestamp": sensor_data.get("timestamp"),
                "sensor_id": sensor_data.get("sensor_id"),
                "location": sensor_data.get("location"),
                "detection_methods": ["threshold"] + (["zscore"] if self.use_zscore else []),
            },
        }
        
        return result
    
    def reset_history(self, sensor_name: str | None = None) -> None:
        """
        Reset sensor history for z-score calculations.
        
        Args:
            sensor_name: Specific sensor to reset, or None to reset all
        """
        if sensor_name:
            if sensor_name in self.sensor_history:
                del self.sensor_history[sensor_name]
        else:
            self.sensor_history.clear()


def detect_anomalies(sensor_data: dict, use_zscore: bool = False) -> dict[str, Any]:
    """
    Convenience function for one-off anomaly detection.
    
    Note: Z-score detection requires historical data, so it's less useful
    for single readings. Use the AnomalyDetector class for continuous monitoring.
    
    Args:
        sensor_data: Sensor data dictionary
        use_zscore: Enable z-score detection (not recommended for single calls)
    
    Returns:
        Detection result dictionary
    
    Example:
        from sensor_simulator import get_single_reading
        from anomaly_detector import detect_anomalies
        
        data = get_single_reading()
        result = detect_anomalies(data)
        
        if result["anomaly_detected"]:
            print(f"Alert! Sensors triggered: {result['triggered_sensors']}")
    """
    detector = AnomalyDetector(use_zscore=use_zscore)
    return detector.analyze(sensor_data)


# Demo and testing
if __name__ == "__main__":
    import time
    
    # Try to import from sensor_simulator if available
    try:
        from sensor_simulator import generate_sensor_data
        use_simulator = True
    except ImportError:
        use_simulator = False
        print("Note: sensor_simulator not found, using mock data\n")
    
    def generate_mock_data():
        """Generate mock sensor data for testing."""
        import random
        from datetime import datetime, timezone
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sensor_id": "TEST-001",
            "location": "test_lab",
            "readings": {
                "temperature": {"value": random.uniform(10, 40), "unit": "°C"},
                "gas": {"value": random.uniform(0, 100), "unit": "ppm"},
                "vibration": {"value": random.uniform(0, 6), "unit": "mm/s"},
                "cpu_usage": {"value": random.uniform(0, 100), "unit": "%"},
            },
        }
    
    print("Anomaly Detector Demo")
    print("=" * 60)
    print("Running with z-score enabled (needs ~10 samples to calibrate)\n")
    
    detector = AnomalyDetector(use_zscore=True)
    
    # Run for 15 iterations to demonstrate z-score learning
    for i in range(15):
        if use_simulator:
            data = generate_sensor_data()
        else:
            data = generate_mock_data()
        
        result = detector.analyze(data)
        
        print(f"[Sample {i + 1}] {data['timestamp'][:19]}")
        
        if result["anomaly_detected"]:
            print(f"  ⚠️  ANOMALY DETECTED: {result['triggered_sensors']}")
            for sensor, details in result["summary"].items():
                print(f"      {sensor}: {details['value']} {details['unit']}")
                print(f"        Reasons: {', '.join(details['reasons'])}")
        else:
            print("  ✓  All sensors normal")
        
        # Show z-score calibration progress
        if i < MIN_SAMPLES_FOR_ZSCORE:
            print(f"  📊 Z-score calibrating: {i + 1}/{MIN_SAMPLES_FOR_ZSCORE} samples")
        
        print()
        time.sleep(0.5)  # Short delay for demo
    
    print("=" * 60)
    print("Demo complete. In production, run continuously with sensor_simulator.")
