"""
Breach Correlator - Upside Down Severity Scoring

Computes a single "Upside Down breach" severity (1-10) from multi-sensor
anomaly results. Multiple sensors triggering = higher breach level.
"""

from dataclasses import dataclass
from typing import Any


# Severity labels for display
BREACH_LEVEL_LABELS = {
    0: "All clear",
    1: "Minor fluctuation",
    2: "Elevated",
    3: "Unusual activity",
    4: "Gate resonance",
    5: "Dimensional stress",
    6: "Portal instability",
    7: "Breach imminent",
    8: "Upside Down contact",
    9: "Full breach",
    10: "Critical — evacuate",
}


@dataclass
class BreachAssessment:
    """Result of breach correlation."""
    level: int  # 0-10
    label: str
    triggered_sensors: list[str]
    num_triggered: int
    is_multi_sensor: bool
    recommendation: str


def compute_breach_level(anomaly_result: dict[str, Any]) -> BreachAssessment:
    """
    Compute Upside Down breach severity from anomaly detection result.

    Args:
        anomaly_result: Dict from anomaly_detector.analyze() with
            anomaly_detected, triggered_sensors, summary

    Returns:
        BreachAssessment with level 0-10, label, and recommendation
    """
    triggered = anomaly_result.get("triggered_sensors", [])
    summary = anomaly_result.get("summary", {})
    num = len(triggered)

    # Base level from number of sensors (1 sensor = 2, 2 = 4, 3 = 6, 4 = 8)
    # Plus bump if any sensor is severely out of range (from summary)
    level = 0
    if num == 0:
        level = 0
    elif num == 1:
        level = 2
    elif num == 2:
        level = 4
    elif num == 3:
        level = 6
    else:
        level = 8

    # Critical sensors (temperature, gas) add +1 each when triggered
    critical_sensors = {"temperature", "gas"}
    for s in triggered:
        if s in critical_sensors:
            level = min(10, level + 1)

    level = min(10, level)
    label = BREACH_LEVEL_LABELS.get(level, "Unknown")
    is_multi = num >= 2

    if level == 0:
        rec = "Continue standard monitoring."
    elif level <= 3:
        rec = "Increase scan frequency. Watch for additional triggers."
    elif level <= 6:
        rec = "Alert Hawkins Lab security. Prepare containment protocols."
    elif level <= 8:
        rec = "Initiate lockdown procedures. Contact Eleven."
    else:
        rec = "EVACUATE. Full Upside Down breach protocol."

    return BreachAssessment(
        level=level,
        label=label,
        triggered_sensors=triggered,
        num_triggered=num,
        is_multi_sensor=is_multi,
        recommendation=rec,
    )
