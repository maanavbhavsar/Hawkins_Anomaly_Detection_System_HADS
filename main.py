"""
Hawkins Lab: Interdimensional Anomaly Detection

Main pipeline: simulate lab sensors → detect anomalies → compute breach level
→ AWS Bedrock (Stranger Things explanations) → Datadog metrics & alerts.

Run: python main.py
"""

import os
import signal
import time
from datetime import datetime, timezone
from dateutil import parser as date_parser

from dotenv import load_dotenv

from sensor_simulator import generate_sensor_data
from anomaly_detector import AnomalyDetector, THRESHOLDS
from breach_correlator import compute_breach_level, BreachAssessment
from aws_bedrock_integration import (
    StrangerThingsAnalyzer,
    AnomalyData,
    get_fallback_explanation,
)
from datadog_metrics import DatadogMetricsClient, send_metrics_and_check_anomaly

load_dotenv()

# -----------------------------------------------------------------------------
# Config (env or defaults)
# -----------------------------------------------------------------------------
SENSOR_ID = os.getenv("SENSOR_ID", "HAWKINS-LAB-001")
LOCATION = os.getenv("LOCATION", "main_lab")
INTERVAL_SECONDS = float(os.getenv("POLLING_INTERVAL", "5.0"))
ENABLE_BEDROCK = os.getenv("ENABLE_BEDROCK", "true").lower() == "true"
ENABLE_DATADOG = os.getenv("ENABLE_DATADOG", "true").lower() == "true"


def _parse_timestamp(ts: str | None) -> datetime:
    if ts is None:
        return datetime.now(timezone.utc)
    try:
        return date_parser.isoparse(ts)
    except Exception:
        return datetime.now(timezone.utc)


def anomaly_result_to_anomaly_data_list(
    anomaly_result: dict,
    sensor_data: dict,
) -> list[AnomalyData]:
    """Convert anomaly_detector result + sensor_data to list of AnomalyData for Bedrock."""
    out = []
    summary = anomaly_result.get("summary", {})
    sensor_id = sensor_data.get("sensor_id", "LAB-001")
    location = sensor_data.get("location", "main_lab")
    ts = _parse_timestamp(sensor_data.get("timestamp"))

    for sensor_type, details in summary.items():
        value = details.get("value")
        unit = details.get("unit", "")
        thr = details.get("threshold_result", {})
        min_t = thr.get("min_threshold")
        max_t = thr.get("max_threshold")
        if min_t is None or max_t is None:
            cfg = THRESHOLDS.get(sensor_type, {})
            min_t = cfg.get("min", 0.0)
            max_t = cfg.get("max", 100.0)
        severity = "CRITICAL" if len(summary) >= 2 else "WARNING"
        out.append(
            AnomalyData(
                sensor_id=sensor_id,
                sensor_type=sensor_type,
                value=float(value),
                unit=unit,
                threshold_min=float(min_t),
                threshold_max=float(max_t),
                location=location,
                timestamp=ts,
                severity=severity,
            )
        )
    return out


def run_pipeline(
    detector: AnomalyDetector,
    dd_client: DatadogMetricsClient | None,
    bedrock_analyzer: StrangerThingsAnalyzer | None,
    interval_seconds: float,
    sensor_id: str,
    location: str,
    stop_flag: list,
) -> None:
    """Run one iteration: generate data, detect anomalies, send to Datadog/Bedrock."""
    sensor_data = generate_sensor_data(sensor_id=sensor_id, location=location)
    anomaly_result = detector.analyze(sensor_data)
    breach = compute_breach_level(anomaly_result)

    # Console: themed output
    ts_str = sensor_data.get("timestamp", "")[:19].replace("T", " ")
    print(f"\n[{ts_str}] HAWKINS LAB -- {sensor_id} @ {location}")

    for name, r in sensor_data.get("readings", {}).items():
        anomaly_mark = " [ANOMALY]" if r.get("is_anomaly") else ""
        print(f"  {name}: {r.get('value')} {r.get('unit', '')}{anomaly_mark}")

    # Breach level
    bar = "#" * breach.level + "-" * (10 - breach.level)
    print(f"\n  UPSIDE DOWN BREACH LEVEL: [{bar}] {breach.level}/10 -- {breach.label}")
    if breach.recommendation:
        print(f"  >> {breach.recommendation}")

    # Datadog
    if dd_client:
        send_metrics_and_check_anomaly(sensor_data, anomaly_result, dd_client)
        # Breach level as custom metric (if client supports it - we'll add a simple send)
        _send_breach_metric(dd_client, breach, sensor_data)

    if anomaly_result.get("anomaly_detected"):
        title = f"Upside Down breach detected! Level {breach.level}/10 -- {breach.label}"
        if dd_client and dd_client._is_configured():
            dd_client.send_anomaly_alert(anomaly_result, sensor_data, title=title)

    # Bedrock: themed explanation (first anomaly only to save API calls)
    if anomaly_result.get("anomaly_detected"):
        anomaly_list = anomaly_result_to_anomaly_data_list(anomaly_result, sensor_data)
        if anomaly_list:
            first = anomaly_list[0]
            if bedrock_analyzer:
                try:
                    explanation = bedrock_analyzer.explain_anomaly(first)
                except Exception:
                    explanation = None
                if not explanation:
                    explanation = get_fallback_explanation(first)
            else:
                explanation = get_fallback_explanation(first)
            print("\n  HAWKINS AI ANALYSIS:")
            print(f"  \" {explanation} \"")
            try:
                from minimax_voice import speak_alert, build_voice_alert_text
                voice_text = build_voice_alert_text(explanation)
                if speak_alert(voice_text):
                    print("  [Voice alert played]")
            except Exception:
                pass


def _send_breach_metric(dd_client, breach: BreachAssessment, sensor_data: dict) -> None:
    """Send breach level to Datadog if the client exposes a way to send custom metrics."""
    if not getattr(dd_client, "_is_configured", lambda: False)():
        return
    if not getattr(dd_client, "configuration", None):
        return
    try:
        from datadog_api_client import ApiClient
        from datadog_api_client.v2.api.metrics_api import MetricsApi
        from datadog_api_client.v2.model.metric_intake_type import MetricIntakeType
        from datadog_api_client.v2.model.metric_payload import MetricPayload
        from datadog_api_client.v2.model.metric_point import MetricPoint
        from datadog_api_client.v2.model.metric_series import MetricSeries

        ts = int(datetime.now(timezone.utc).timestamp())
        tags = getattr(dd_client, "default_tags", []).copy()
        tags.append(f"sensor_id:{sensor_data.get('sensor_id', 'unknown')}")
        tags.append(f"location:{sensor_data.get('location', 'unknown')}")
        series = [
            MetricSeries(
                metric="lab.breach.level",
                type=MetricIntakeType.GAUGE,
                points=[MetricPoint(timestamp=ts, value=float(breach.level))],
                tags=tags,
            )
        ]
        with ApiClient(dd_client.configuration) as api_client:
            MetricsApi(api_client).submit_metrics(body=MetricPayload(series=series))
    except Exception:
        pass


def main() -> None:
    stop_flag = []

    def _handle(_sig, _frame):
        print("\n\n[STOP] Shutting down Hawkins Lab monitor. Stay safe out there.")
        stop_flag.append(True)

    signal.signal(signal.SIGINT, _handle)
    signal.signal(signal.SIGTERM, _handle)

    print("=" * 60)
    print("[LAB] HAWKINS NATIONAL LABORATORY")
    print("   Interdimensional Anomaly Detection System")
    print("=" * 60)
    print(f"   Sensor: {SENSOR_ID} @ {LOCATION}")
    print(f"   Interval: {INTERVAL_SECONDS}s")
    print(f"   Bedrock: {'ON' if ENABLE_BEDROCK else 'OFF'}  |  Datadog: {'ON' if ENABLE_DATADOG else 'OFF'}")
    print("=" * 60)
    print("\nPress Ctrl+C to stop.\n")

    detector = AnomalyDetector(use_zscore=True)
    dd_client = DatadogMetricsClient() if ENABLE_DATADOG else None
    bedrock_analyzer = None
    if ENABLE_BEDROCK:
        try:
            bedrock_analyzer = StrangerThingsAnalyzer()
        except Exception as e:
            print(f"[!] Bedrock unavailable: {e}. Using fallback explanations.\n")
            bedrock_analyzer = None

    while not stop_flag:
        run_pipeline(
            detector=detector,
            dd_client=dd_client,
            bedrock_analyzer=bedrock_analyzer,
            interval_seconds=INTERVAL_SECONDS,
            sensor_id=SENSOR_ID,
            location=LOCATION,
            stop_flag=stop_flag,
        )
        for _ in range(int(INTERVAL_SECONDS * 10)):
            if stop_flag:
                break
            time.sleep(0.1)

    print("\nGoodbye from Hawkins Lab.\n")


if __name__ == "__main__":
    main()
