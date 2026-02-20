"""
Datadog Metrics Module
======================
Sends lab sensor data and anomaly alerts to Datadog.

Features:
- Submit custom metrics for all sensor readings
- Create events/alerts when anomalies are detected
- Programmatically create monitoring dashboards
- Track anomaly counts and detection statistics

Setup:
------
1. Install the Datadog API client:
   pip install datadog-api-client

2. Set your API keys (see CONFIGURATION section below)

3. Import and use:
   from datadog_metrics import DatadogMetricsClient
   
   client = DatadogMetricsClient()
   client.send_sensor_metrics(sensor_data)

Metrics Created:
---------------
- lab.sensor.temperature (gauge) - Temperature in °C
- lab.sensor.gas (gauge) - Gas concentration in ppm
- lab.sensor.vibration (gauge) - Vibration in mm/s
- lab.sensor.cpu_usage (gauge) - CPU usage percentage
- lab.anomaly.detected (count) - Anomaly occurrence counter
- lab.anomaly.sensors_triggered (gauge) - Number of sensors in anomaly state

Adding More Metrics:
-------------------
To add a new metric, update the METRIC_CONFIG dictionary:

    METRIC_CONFIG["new_sensor"] = {
        "metric_name": "lab.sensor.new_sensor",
        "type": MetricIntakeType.GAUGE,  # or COUNT, RATE
        "unit": "unit_name",
        "description": "Description for dashboard"
    }

Then ensure your sensor_data includes the new reading.
"""

import os
import time
from datetime import datetime, timezone
from typing import Any

# Datadog API client imports
# Install with: pip install datadog-api-client
try:
    from datadog_api_client import ApiClient, Configuration
    from datadog_api_client.v1.api.events_api import EventsApi
    from datadog_api_client.v1.api.dashboards_api import DashboardsApi
    from datadog_api_client.v1.model.event_create_request import EventCreateRequest
    from datadog_api_client.v1.model.event_alert_type import EventAlertType
    from datadog_api_client.v1.model.dashboard import Dashboard
    from datadog_api_client.v1.model.dashboard_layout_type import DashboardLayoutType
    from datadog_api_client.v1.model.widget import Widget
    from datadog_api_client.v1.model.widget_definition import WidgetDefinition
    from datadog_api_client.v1.model.timeseries_widget_definition import TimeseriesWidgetDefinition
    from datadog_api_client.v1.model.timeseries_widget_definition_type import TimeseriesWidgetDefinitionType
    from datadog_api_client.v1.model.timeseries_widget_request import TimeseriesWidgetRequest
    from datadog_api_client.v1.model.widget_layout import WidgetLayout
    from datadog_api_client.v1.model.formula_and_function_metric_query_definition import FormulaAndFunctionMetricQueryDefinition
    from datadog_api_client.v1.model.formula_and_function_metric_data_source import FormulaAndFunctionMetricDataSource
    from datadog_api_client.v2.api.metrics_api import MetricsApi
    from datadog_api_client.v2.model.metric_intake_type import MetricIntakeType
    from datadog_api_client.v2.model.metric_payload import MetricPayload
    from datadog_api_client.v2.model.metric_point import MetricPoint
    from datadog_api_client.v2.model.metric_series import MetricSeries
    DATADOG_AVAILABLE = True
except ImportError:
    DATADOG_AVAILABLE = False
    print("Warning: datadog-api-client not installed. Run: pip install datadog-api-client")


# =============================================================================
# CONFIGURATION - Set your Datadog API keys here
# =============================================================================
# Option 1: Set environment variables (recommended for production)
#   export DD_API_KEY="your_api_key_here"
#   export DD_APP_KEY="your_app_key_here"
#
# Option 2: Set directly in code (for development only - don't commit!)
#   DATADOG_API_KEY = "your_api_key_here"
#   DATADOG_APP_KEY = "your_app_key_here"

DATADOG_API_KEY = os.environ.get("DD_API_KEY", "YOUR_API_KEY_HERE")
DATADOG_APP_KEY = os.environ.get("DD_APP_KEY", "YOUR_APP_KEY_HERE")

# Datadog site (e.g., "datadoghq.com", "datadoghq.eu", "us5.datadoghq.com")
DATADOG_SITE = os.environ.get("DD_SITE", "datadoghq.com")

# Metric prefix for all lab sensor metrics
METRIC_PREFIX = "lab"

# Default tags applied to all metrics
DEFAULT_TAGS = [
    "env:hackathon",
    "project:aws-datadog-lab",
    "source:sensor_simulator",
]


# =============================================================================
# METRIC CONFIGURATION
# =============================================================================
# Define metrics for each sensor type
# To add new metrics: add an entry here and include in sensor_data readings

SENSOR_METRICS = {
    "temperature": {
        "metric_name": f"{METRIC_PREFIX}.sensor.temperature",
        "unit": "celsius",
        "description": "Lab temperature sensor reading",
    },
    "gas": {
        "metric_name": f"{METRIC_PREFIX}.sensor.gas",
        "unit": "ppm",
        "description": "Gas concentration sensor reading",
    },
    "vibration": {
        "metric_name": f"{METRIC_PREFIX}.sensor.vibration",
        "unit": "millimeters_per_second",
        "description": "Vibration sensor reading",
    },
    "cpu_usage": {
        "metric_name": f"{METRIC_PREFIX}.sensor.cpu_usage",
        "unit": "percent",
        "description": "CPU usage percentage",
    },
}

# Anomaly tracking metrics
ANOMALY_METRICS = {
    "detected": f"{METRIC_PREFIX}.anomaly.detected",
    "sensors_triggered": f"{METRIC_PREFIX}.anomaly.sensors_triggered",
}


class DatadogMetricsClient:
    """
    Client for sending sensor metrics and anomaly alerts to Datadog.
    
    Usage:
        client = DatadogMetricsClient()
        
        # Send sensor readings
        client.send_sensor_metrics(sensor_data)
        
        # Send anomaly alert
        client.send_anomaly_alert(anomaly_result)
        
        # Create dashboard (one-time setup)
        dashboard_url = client.create_sensor_dashboard()
    
    Alert Types Available:
    ---------------------
    You can customize alert severity in send_anomaly_alert():
    - EventAlertType.ERROR - Critical issues (red)
    - EventAlertType.WARNING - Warnings (yellow)
    - EventAlertType.INFO - Informational (blue)
    - EventAlertType.SUCCESS - Resolved/success (green)
    """
    
    def __init__(
        self,
        api_key: str | None = None,
        app_key: str | None = None,
        site: str | None = None,
        default_tags: list[str] | None = None,
    ):
        """
        Initialize the Datadog client.
        
        Args:
            api_key: Datadog API key (uses env var if not provided)
            app_key: Datadog APP key (uses env var if not provided)
            site: Datadog site domain (uses env var if not provided)
            default_tags: Tags to apply to all metrics
        """
        self.api_key = api_key or DATADOG_API_KEY
        self.app_key = app_key or DATADOG_APP_KEY
        self.site = site or DATADOG_SITE
        self.default_tags = default_tags or DEFAULT_TAGS.copy()
        
        # Validate configuration
        self._validate_config()
        
        # Initialize Datadog configuration
        self.configuration = None
        if DATADOG_AVAILABLE and self._is_configured():
            self.configuration = Configuration()
            self.configuration.api_key["apiKeyAuth"] = self.api_key
            self.configuration.api_key["appKeyAuth"] = self.app_key
            self.configuration.server_variables["site"] = self.site
    
    def _validate_config(self) -> None:
        """Check if API keys are configured."""
        if not DATADOG_AVAILABLE:
            print("[!] Datadog client not available. Install with: pip install datadog-api-client")
        elif not self._is_configured():
            print("[!] Datadog API keys not configured. Set DD_API_KEY and DD_APP_KEY environment variables.")
    
    def _is_configured(self) -> bool:
        """Check if API keys are set (not placeholders)."""
        return (
            self.api_key 
            and self.app_key 
            and "YOUR_" not in self.api_key 
            and "YOUR_" not in self.app_key
        )
    
    def _get_timestamp(self) -> int:
        """Get current Unix timestamp for metric submission."""
        return int(datetime.now(timezone.utc).timestamp())
    
    def send_sensor_metrics(self, sensor_data: dict) -> bool:
        """
        Send sensor readings to Datadog as custom metrics.
        
        Args:
            sensor_data: Dictionary from sensor_simulator.generate_sensor_data()
        
        Returns:
            True if metrics were sent successfully, False otherwise
        
        Metrics Sent:
        - lab.sensor.temperature
        - lab.sensor.gas
        - lab.sensor.vibration
        - lab.sensor.cpu_usage
        
        Each metric is tagged with:
        - sensor_id
        - location
        - anomaly status (true/false)
        
        Adding Custom Metrics:
        ---------------------
        To send additional metrics, add to the series list:
        
            series.append(MetricSeries(
                metric="lab.custom.my_metric",
                type=MetricIntakeType.GAUGE,
                points=[MetricPoint(timestamp=timestamp, value=my_value)],
                tags=tags
            ))
        """
        if not DATADOG_AVAILABLE or not self._is_configured():
            return self._log_mock_metrics(sensor_data)
        
        readings = sensor_data.get("readings", {})
        timestamp = self._get_timestamp()
        
        # Build tags for this submission
        tags = self.default_tags.copy()
        tags.append(f"sensor_id:{sensor_data.get('sensor_id', 'unknown')}")
        tags.append(f"location:{sensor_data.get('location', 'unknown')}")
        
        # Build metric series for each sensor
        series = []
        
        for sensor_name, config in SENSOR_METRICS.items():
            reading = readings.get(sensor_name, {})
            value = reading.get("value")
            
            if value is not None:
                # Add anomaly status tag for this specific sensor
                sensor_tags = tags.copy()
                sensor_tags.append(f"anomaly:{str(reading.get('is_anomaly', False)).lower()}")
                
                series.append(
                    MetricSeries(
                        metric=config["metric_name"],
                        type=MetricIntakeType.GAUGE,
                        points=[MetricPoint(timestamp=timestamp, value=float(value))],
                        tags=sensor_tags,
                        unit=config.get("unit"),
                    )
                )
        
        # Add overall anomaly flag as a metric (1 = anomaly, 0 = normal)
        has_anomaly = sensor_data.get("has_anomaly", False)
        series.append(
            MetricSeries(
                metric=ANOMALY_METRICS["detected"],
                type=MetricIntakeType.COUNT,
                points=[MetricPoint(timestamp=timestamp, value=1.0 if has_anomaly else 0.0)],
                tags=tags,
            )
        )
        
        # Submit metrics to Datadog
        try:
            with ApiClient(self.configuration) as api_client:
                api_instance = MetricsApi(api_client)
                payload = MetricPayload(series=series)
                api_instance.submit_metrics(body=payload)
                return True
        except Exception as e:
            print(f"Error sending metrics to Datadog: {e}")
            return False
    
    def send_anomaly_alert(
        self,
        anomaly_result: dict,
        sensor_data: dict | None = None,
        title: str = "Upside Down breach detected!",
        priority: str = "normal",
    ) -> bool:
        """
        Send an alert event to Datadog when anomaly is detected.
        
        Args:
            anomaly_result: Dictionary from anomaly_detector.analyze()
            sensor_data: Optional sensor data for additional context
            title: Alert title (default: "Upside Down breach detected!")
            priority: Event priority ("normal" or "low")
        
        Returns:
            True if event was sent successfully, False otherwise
        
        Customizing Alerts:
        ------------------
        You can customize the alert by modifying the EventCreateRequest:
        
        - alert_type: ERROR (red), WARNING (yellow), INFO (blue), SUCCESS (green)
        - priority: "normal" or "low"
        - tags: Add custom tags for filtering in Datadog
        
        To add different alert types for different anomaly severities:
        
            severity = len(anomaly_result["triggered_sensors"])
            if severity >= 3:
                alert_type = EventAlertType.ERROR
            elif severity >= 2:
                alert_type = EventAlertType.WARNING
            else:
                alert_type = EventAlertType.INFO
        """
        if not anomaly_result.get("anomaly_detected"):
            return False  # No anomaly, no alert needed
        
        # Build alert message
        triggered = anomaly_result.get("triggered_sensors", [])
        summary = anomaly_result.get("summary", {})
        
        # Format detailed message
        message_lines = [
            "## Anomaly Detection Alert",
            "",
            f"**Triggered Sensors:** {', '.join(triggered)}",
            "",
            "### Sensor Details:",
        ]
        
        for sensor_name, details in summary.items():
            value = details.get("value", "N/A")
            unit = details.get("unit", "")
            reasons = ", ".join(details.get("reasons", []))
            message_lines.append(f"- **{sensor_name}**: {value} {unit} ({reasons})")
        
        # Add metadata
        metadata = anomaly_result.get("metadata", {})
        message_lines.extend([
            "",
            "### Metadata:",
            f"- Sensor ID: {metadata.get('sensor_id', 'unknown')}",
            f"- Location: {metadata.get('location', 'unknown')}",
            f"- Timestamp: {metadata.get('timestamp', 'unknown')}",
            f"- Detection Methods: {', '.join(metadata.get('detection_methods', []))}",
        ])
        
        message = "\n".join(message_lines)
        
        if not DATADOG_AVAILABLE or not self._is_configured():
            return self._log_mock_alert(title, message, triggered)
        
        # Build tags
        tags = self.default_tags.copy()
        tags.append(f"sensor_id:{metadata.get('sensor_id', 'unknown')}")
        tags.append(f"location:{metadata.get('location', 'unknown')}")
        tags.append("alert_type:anomaly")
        for sensor in triggered:
            tags.append(f"triggered_sensor:{sensor}")
        
        # Determine alert severity based on number of triggered sensors
        # You can customize this logic for your needs
        num_triggered = len(triggered)
        if num_triggered >= 3:
            alert_type = EventAlertType.ERROR
        elif num_triggered >= 2:
            alert_type = EventAlertType.WARNING
        else:
            alert_type = EventAlertType.WARNING
        
        try:
            with ApiClient(self.configuration) as api_client:
                api_instance = EventsApi(api_client)
                event = EventCreateRequest(
                    title=title,
                    text=message,
                    alert_type=alert_type,
                    priority=priority,
                    tags=tags,
                    source_type_name="python",
                )
                api_instance.create_event(body=event)
                return True
        except Exception as e:
            print(f"Error sending alert to Datadog: {e}")
            return False
    
    def create_sensor_dashboard(self, dashboard_name: str = "Lab Sensor Monitoring") -> str | None:
        """
        Create a Datadog dashboard with line charts for all sensors.
        
        Args:
            dashboard_name: Name for the dashboard
        
        Returns:
            Dashboard URL if created successfully, None otherwise
        
        Dashboard Contents:
        ------------------
        - Temperature line chart
        - Gas concentration line chart
        - Vibration line chart
        - CPU usage line chart
        - Anomaly event overlay
        
        Customizing the Dashboard:
        -------------------------
        To add more widgets, append to the widgets list:
        
            widgets.append(Widget(
                definition=TimeseriesWidgetDefinition(
                    title="My Custom Widget",
                    type=TimeseriesWidgetDefinitionType.TIMESERIES,
                    requests=[TimeseriesWidgetRequest(
                        queries=[FormulaAndFunctionMetricQueryDefinition(
                            data_source=FormulaAndFunctionMetricDataSource.METRICS,
                            query="avg:lab.custom.metric{*}",
                            name="custom"
                        )],
                        response_format="timeseries",
                        display_type="line"
                    )]
                ),
                layout=WidgetLayout(x=0, y=8, width=6, height=4)
            ))
        
        Widget Types Available:
        - timeseries: Line/area/bar charts over time
        - query_value: Single number display
        - toplist: Top N items
        - heatmap: Heat map visualization
        - distribution: Distribution graph
        """
        if not DATADOG_AVAILABLE or not self._is_configured():
            return self._log_mock_dashboard(dashboard_name)
        
        widgets = []
        
        # Create a widget for each sensor metric
        widget_configs = [
            {"sensor": "temperature", "title": "🌡️ Temperature (°C)", "x": 0, "y": 0, "color": "orange"},
            {"sensor": "gas", "title": "💨 Gas Concentration (ppm)", "x": 6, "y": 0, "color": "purple"},
            {"sensor": "vibration", "title": "📳 Vibration (mm/s)", "x": 0, "y": 4, "color": "blue"},
            {"sensor": "cpu_usage", "title": "💻 CPU Usage (%)", "x": 6, "y": 4, "color": "green"},
        ]
        
        for config in widget_configs:
            sensor = config["sensor"]
            metric_name = SENSOR_METRICS[sensor]["metric_name"]
            
            widget = Widget(
                definition=TimeseriesWidgetDefinition(
                    title=config["title"],
                    type=TimeseriesWidgetDefinitionType.TIMESERIES,
                    requests=[
                        TimeseriesWidgetRequest(
                            queries=[
                                FormulaAndFunctionMetricQueryDefinition(
                                    data_source=FormulaAndFunctionMetricDataSource.METRICS,
                                    query=f"avg:{metric_name}{{*}}",
                                    name=sensor,
                                )
                            ],
                            response_format="timeseries",
                            display_type="line",
                        )
                    ],
                    show_legend=True,
                ),
                layout=WidgetLayout(
                    x=config["x"],
                    y=config["y"],
                    width=6,
                    height=4,
                ),
            )
            widgets.append(widget)
        
        # Add anomaly count widget
        anomaly_widget = Widget(
            definition=TimeseriesWidgetDefinition(
                title="⚠️ Anomaly Detection Count",
                type=TimeseriesWidgetDefinitionType.TIMESERIES,
                requests=[
                    TimeseriesWidgetRequest(
                        queries=[
                            FormulaAndFunctionMetricQueryDefinition(
                                data_source=FormulaAndFunctionMetricDataSource.METRICS,
                                query=f"sum:{ANOMALY_METRICS['detected']}{{*}}.as_count()",
                                name="anomalies",
                            )
                        ],
                        response_format="timeseries",
                        display_type="bars",
                    )
                ],
                show_legend=True,
            ),
            layout=WidgetLayout(x=0, y=8, width=12, height=3),
        )
        widgets.append(anomaly_widget)
        
        # Create the dashboard
        dashboard = Dashboard(
            title=dashboard_name,
            description="Real-time monitoring of lab sensor data with anomaly detection. Created by AWS x Datadog Hackathon project.",
            layout_type=DashboardLayoutType.ORDERED,
            widgets=widgets,
        )
        
        try:
            with ApiClient(self.configuration) as api_client:
                api_instance = DashboardsApi(api_client)
                response = api_instance.create_dashboard(body=dashboard)
                dashboard_url = f"https://app.{self.site}/dashboard/{response.id}"
                print(f"Dashboard created: {dashboard_url}")
                return dashboard_url
        except Exception as e:
            print(f"Error creating dashboard: {e}")
            return None
    
    # =========================================================================
    # MOCK LOGGING (when Datadog not configured)
    # =========================================================================
    
    def _log_mock_metrics(self, sensor_data: dict) -> bool:
        """Log metrics locally when Datadog is not configured."""
        readings = sensor_data.get("readings", {})
        print(f"[MOCK] Sending metrics for sensor {sensor_data.get('sensor_id')}:")
        for sensor_name, reading in readings.items():
            metric_name = SENSOR_METRICS.get(sensor_name, {}).get("metric_name", f"unknown.{sensor_name}")
            print(f"  {metric_name}: {reading.get('value')} (anomaly={reading.get('is_anomaly')})")
        return True
    
    def _log_mock_alert(self, title: str, message: str, triggered: list) -> bool:
        """Log alert locally when Datadog is not configured."""
        print(f"\n[MOCK] 🚨 ALERT: {title}")
        print(f"  Triggered sensors: {', '.join(triggered)}")
        print("  (Set DD_API_KEY and DD_APP_KEY to send real alerts)\n")
        return True
    
    def _log_mock_dashboard(self, name: str) -> str:
        """Log dashboard creation locally when Datadog is not configured."""
        print(f"\n[MOCK] 📊 Would create dashboard: {name}")
        print("  Widgets: Temperature, Gas, Vibration, CPU Usage, Anomaly Count")
        print("  (Set DD_API_KEY and DD_APP_KEY to create real dashboard)\n")
        return "https://app.datadoghq.com/dashboard/mock-dashboard-id"


def send_metrics_and_check_anomaly(
    sensor_data: dict,
    anomaly_result: dict,
    client: DatadogMetricsClient | None = None,
) -> dict[str, bool]:
    """
    Convenience function to send metrics and alerts in one call.
    
    Args:
        sensor_data: Dictionary from sensor_simulator.generate_sensor_data()
        anomaly_result: Dictionary from anomaly_detector.analyze()
        client: Optional existing client (creates new one if not provided)
    
    Returns:
        Dictionary with success status for each operation
    
    Example:
        from sensor_simulator import generate_sensor_data
        from anomaly_detector import AnomalyDetector, detect_anomalies
        from datadog_metrics import send_metrics_and_check_anomaly
        
        data = generate_sensor_data()
        result = detect_anomalies(data)
        
        status = send_metrics_and_check_anomaly(data, result)
        print(f"Metrics sent: {status['metrics_sent']}")
        print(f"Alert sent: {status['alert_sent']}")
    """
    if client is None:
        client = DatadogMetricsClient()
    
    metrics_sent = client.send_sensor_metrics(sensor_data)
    alert_sent = False
    
    if anomaly_result.get("anomaly_detected"):
        alert_sent = client.send_anomaly_alert(anomaly_result, sensor_data)
    
    return {
        "metrics_sent": metrics_sent,
        "alert_sent": alert_sent,
    }


# Demo and testing
if __name__ == "__main__":
    print("Datadog Metrics Module Demo")
    print("=" * 60)
    
    # Check configuration status
    client = DatadogMetricsClient()
    
    if not client._is_configured():
        print("\n⚠️  Running in MOCK mode (API keys not configured)")
        print("   To send real metrics, set environment variables:")
        print("   - DD_API_KEY=your_api_key")
        print("   - DD_APP_KEY=your_app_key")
        print()
    
    # Try to import from other modules
    try:
        from sensor_simulator import generate_sensor_data
        from anomaly_detector import AnomalyDetector
        modules_available = True
    except ImportError:
        modules_available = False
        print("Note: sensor_simulator or anomaly_detector not found")
        print("Using mock data for demo\n")
    
    if modules_available:
        # Run a demo with real modules
        detector = AnomalyDetector(use_zscore=False)
        
        print("Sending 5 sample readings...\n")
        
        for i in range(5):
            # Generate sensor data
            data = generate_sensor_data()
            
            # Detect anomalies
            result = detector.analyze(data)
            
            # Send to Datadog
            status = send_metrics_and_check_anomaly(data, result, client)
            
            anomaly_indicator = "⚠️ ANOMALY" if result["anomaly_detected"] else "✓ Normal"
            print(f"[{i + 1}] {anomaly_indicator} - Metrics: {status['metrics_sent']}, Alert: {status['alert_sent']}")
            
            time.sleep(1)
        
        print("\n" + "=" * 60)
        print("Creating dashboard...")
        dashboard_url = client.create_sensor_dashboard()
        
    else:
        # Use mock data
        mock_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sensor_id": "DEMO-001",
            "location": "demo_lab",
            "has_anomaly": True,
            "readings": {
                "temperature": {"value": 45.5, "unit": "°C", "is_anomaly": True},
                "gas": {"value": 25.0, "unit": "ppm", "is_anomaly": False},
                "vibration": {"value": 1.5, "unit": "mm/s", "is_anomaly": False},
                "cpu_usage": {"value": 55.0, "unit": "%", "is_anomaly": False},
            },
        }
        
        mock_anomaly = {
            "anomaly_detected": True,
            "triggered_sensors": ["temperature"],
            "summary": {
                "temperature": {
                    "value": 45.5,
                    "unit": "°C",
                    "reasons": ["threshold_above_max"],
                }
            },
            "metadata": {
                "timestamp": mock_data["timestamp"],
                "sensor_id": "DEMO-001",
                "location": "demo_lab",
                "detection_methods": ["threshold"],
            },
        }
        
        print("Sending mock data...\n")
        status = send_metrics_and_check_anomaly(mock_data, mock_anomaly, client)
        
        print("\nCreating dashboard...")
        client.create_sensor_dashboard()
    
    print("\nDemo complete!")
