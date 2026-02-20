"""
AWS Bedrock Integration Module - Stranger Things Edition

This module connects to AWS Bedrock to generate Stranger Things-themed
explanations for lab sensor anomalies. Think Hawkins National Laboratory
meets modern cloud AI.

Example output:
    "Warning! Interdimensional breach detected in Lab 1. 
     Magnetic flux is spiking abnormally. The Upside Down may be leaking through."
"""

import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv()


# =============================================================================
# CONFIGURATION PLACEHOLDERS - Modify these for your setup
# =============================================================================

# AWS Credentials (can also be set via environment variables or IAM roles)
# For short-term/temporary credentials (e.g. SSO, assumed role), also set AWS_SESSION_TOKEN.
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID", "YOUR_ACCESS_KEY_HERE")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "YOUR_SECRET_KEY_HERE")
AWS_SESSION_TOKEN = os.getenv("AWS_SESSION_TOKEN", "")  # Optional; use for temporary credentials

# AWS Region where Bedrock is available
# Options: us-east-1, us-west-2, eu-west-1, ap-northeast-1, etc.
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Bedrock Model Configuration
# Available Claude models on Bedrock:
#   - anthropic.claude-opus-4-6-v1              (Opus 4.6 - most capable, latest)
#   - anthropic.claude-3-opus-20240229-v1:0    (Opus 3 - previous generation)
#   - anthropic.claude-3-sonnet-20240229-v1:0  (balanced)
#   - anthropic.claude-3-haiku-20240307-v1:0   (fastest)
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", "anthropic.claude-opus-4-6-v1")

# Model Parameters - Optimized for Opus 4.6
# Opus 4.6 supports extended thinking and adaptive thinking modes
MODEL_MAX_TOKENS = 512      # Maximum response length (sufficient for 2-3 sentence warnings)
MODEL_TEMPERATURE = 0.7     # Balanced creativity (0.0 = deterministic, 1.0 = creative)
MODEL_TOP_P = 0.95          # Nucleus sampling parameter (higher for Opus 4.6 quality)


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class AnomalyData:
    """
    Represents a sensor anomaly to be explained.
    
    Attributes:
        sensor_id: Unique identifier for the sensor (e.g., "SENSOR-001")
        sensor_type: Type of measurement (temperature, humidity, pressure, etc.)
        value: The anomalous reading value
        unit: Unit of measurement (°C, %, hPa, ppm, etc.)
        threshold_min: Lower bound of normal range
        threshold_max: Upper bound of normal range
        location: Physical location of the sensor
        timestamp: When the anomaly was detected
        severity: Alert level (WARNING, CRITICAL)
    """
    sensor_id: str
    sensor_type: str
    value: float
    unit: str
    threshold_min: float
    threshold_max: float
    location: str
    timestamp: datetime
    severity: str = "WARNING"


# =============================================================================
# STRANGER THINGS THEMED PROMPT TEMPLATE
# =============================================================================

STRANGER_THINGS_PROMPT = """<role>
You are Dr. Martin Brenner, a senior scientist at Hawkins National Laboratory in 1983. You've witnessed firsthand the terrifying phenomena from the Upside Down—the parallel dimension that threatens our reality. Your expertise lies in detecting and interpreting interdimensional anomalies through lab sensor monitoring.
</role>

<context>
Hawkins National Laboratory conducts classified experiments involving psychic abilities and interdimensional research. The Upside Down is a dark, parallel dimension that occasionally breaches into our world, causing electromagnetic disturbances, temperature fluctuations, and other anomalous sensor readings.

Key Stranger Things terminology to use:
- The Upside Down: The parallel dark dimension
- Demogorgons: Predatory creatures from the Upside Down
- Mind Flayer: A powerful entity controlling the Upside Down
- Eleven (El): A test subject with psychic powers
- Gate/Portal: Dimensional breaches between worlds
- Electromagnetic disturbances: Signature of interdimensional activity
- Hawkins Lab experiments: Classified research gone wrong
</context>

<task>
Analyze the sensor anomaly data below and generate a dramatic, in-character warning message that:
1. Sounds authentically like dialogue from the Stranger Things TV series
2. Maintains the paranoid, urgent tone of a scientist who has seen too much
3. Connects the specific sensor reading to interdimensional phenomena
4. References appropriate Stranger Things elements based on sensor type
</task>

<sensor_data>
Sensor ID: {sensor_id}
Sensor Type: {sensor_type}
Location: {location}
Current Reading: {value} {unit}
Normal Operating Range: {threshold_min} to {threshold_max} {unit}
Severity Level: {severity}
Detection Timestamp: {timestamp}
</sensor_data>

<output_requirements>
- Format: A single warning message, 2-3 sentences maximum
- Style: Urgent, dramatic, paranoid scientist tone
- Content: Must reference the specific sensor type, location, and reading value
- Theme: Connect anomaly to Stranger Things lore (Upside Down, creatures, experiments, etc.)
- Tone: Professional but alarmed, like a scientist reporting to superiors
- Length: Concise but impactful (aim for 40-80 words)
- Output: ONLY the warning message text, no prefixes, no explanations, no markdown
</output_requirements>

<examples>
Example 1 (Temperature anomaly):
"Warning! Thermal spike detected in Lab-A: temperature reading 45.2°C exceeds normal parameters. This matches the electromagnetic signature we observed before the Gate opened in '83. Recommend immediate containment protocols and alert Dr. Owens."

Example 2 (Gas/Vibration anomaly):
"Alert! Atmospheric disturbance in Sector 7: gas readings at 120 ppm indicate possible interdimensional breach. The Upside Down is bleeding through—we need Eleven's assistance immediately."

Example 3 (Multi-sensor critical):
"Critical alert! Multiple sensor anomalies detected simultaneously—this pattern matches previous Gate formations. The Mind Flayer may be attempting another breach. Initiate lockdown protocol immediately."
</examples>

Generate the warning message now:"""


# =============================================================================
# BEDROCK CLIENT CLASS
# =============================================================================

class StrangerThingsAnalyzer:
    """
    AWS Bedrock client that generates Stranger Things-themed anomaly explanations.
    
    Usage:
        analyzer = StrangerThingsAnalyzer()
        
        anomaly = AnomalyData(
            sensor_id="SENSOR-001",
            sensor_type="temperature",
            value=42.5,
            unit="°C",
            threshold_min=18.0,
            threshold_max=28.0,
            location="Lab-A",
            timestamp=datetime.now(),
            severity="CRITICAL"
        )
        
        explanation = analyzer.explain_anomaly(anomaly)
        print(explanation)
        # Output: "Warning! Interdimensional breach detected in Lab-A..."
    """

    def __init__(
        self,
        model_id: str = BEDROCK_MODEL_ID,
        region: str = AWS_REGION,
        max_tokens: int = MODEL_MAX_TOKENS,
        temperature: float = MODEL_TEMPERATURE,
    ):
        """
        Initialize the Bedrock analyzer.
        
        Args:
            model_id: The Bedrock model identifier to use
            region: AWS region where Bedrock is deployed
            max_tokens: Maximum tokens in the response
            temperature: Controls randomness (0.0 = deterministic, 1.0 = creative)
        """
        self.model_id = model_id
        self.region = region
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.client = self._create_client()

    def _create_client(self):
        """
        Create the Bedrock runtime client.
        
        Supports long-term credentials (access key + secret) or short-term
        temporary credentials (access key + secret + session token).
        """
        kwargs = {
            "region_name": self.region,
            "aws_access_key_id": AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": AWS_SECRET_ACCESS_KEY,
        }
        if AWS_SESSION_TOKEN:
            kwargs["aws_session_token"] = AWS_SESSION_TOKEN
        return boto3.client("bedrock-runtime", **kwargs)

    def _build_prompt(self, anomaly: AnomalyData) -> str:
        """
        Build the prompt with anomaly data inserted.
        
        Modify STRANGER_THINGS_PROMPT above to change the theme/style.
        """
        return STRANGER_THINGS_PROMPT.format(
            sensor_id=anomaly.sensor_id,
            sensor_type=anomaly.sensor_type,
            location=anomaly.location,
            value=anomaly.value,
            unit=anomaly.unit,
            threshold_min=anomaly.threshold_min,
            threshold_max=anomaly.threshold_max,
            severity=anomaly.severity,
            timestamp=anomaly.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        )

    def explain_anomaly(self, anomaly: AnomalyData) -> Optional[str]:
        """
        Generate a Stranger Things-themed explanation for a sensor anomaly.
        
        Args:
            anomaly: The anomaly data to explain
            
        Returns:
            A dramatic, themed explanation string, or None if the API call fails
            
        Example:
            >>> explanation = analyzer.explain_anomaly(anomaly)
            >>> print(explanation)
            "Warning! Interdimensional breach detected in Lab-A. Temperature 
             readings are off the charts—this is exactly what happened before 
             the Gate opened. Recommend immediate evacuation and contacting Eleven."
        """
        prompt = self._build_prompt(anomaly)

        try:
            # Build the request body for Claude Opus 4.6 on Bedrock
            # Opus 4.6 supports extended thinking and adaptive thinking modes
            # Using structured prompt format optimized for Opus 4.6's capabilities
            # Inference profile / some models do not allow both temperature and top_p
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                # Opus 4.6 specific optimizations:
                # - Structured XML tags in prompt improve parsing
                # - Clear role/context/task separation enhances understanding
                # - Examples guide the model toward desired output format
            }

            # Call Bedrock API
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType="application/json",
                accept="application/json",
            )

            # Parse response
            response_body = json.loads(response["body"].read())
            return response_body["content"][0]["text"]

        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_msg = e.response["Error"]["Message"]
            print(f"[Bedrock Error] {error_code}: {error_msg}")
            return None
        except Exception as e:
            print(f"[Error] Failed to call Bedrock: {e}")
            return None

    def explain_multiple_anomalies(self, anomalies: list[AnomalyData]) -> list[str]:
        """
        Generate explanations for multiple anomalies.
        
        Args:
            anomalies: List of anomaly data objects
            
        Returns:
            List of themed explanation strings
        """
        explanations = []
        for anomaly in anomalies:
            explanation = self.explain_anomaly(anomaly)
            if explanation:
                explanations.append(explanation)
        return explanations


# =============================================================================
# FALLBACK RESPONSES (when Bedrock is unavailable)
# =============================================================================

def get_fallback_explanation(anomaly: AnomalyData) -> str:
    """
    Generate a fallback Stranger Things-themed message without calling Bedrock.
    Useful for testing or when the API is unavailable.
    """
    templates = {
        "temperature": (
            f"Warning! Thermal anomaly detected in {anomaly.location}. "
            f"Temperature spiked to {anomaly.value}{anomaly.unit}—the same readings "
            "we saw before the Demogorgon emerged. The Upside Down is bleeding through."
        ),
        "humidity": (
            f"Alert! Moisture levels in {anomaly.location} have reached {anomaly.value}{anomaly.unit}. "
            "This atmospheric disturbance matches the conditions when the Gate first opened. "
            "Something from the other side is trying to cross over."
        ),
        "pressure": (
            f"Critical! Barometric pressure in {anomaly.location} dropping to {anomaly.value}{anomaly.unit}. "
            "We're detecting the same vacuum effect that preceded the Mind Flayer's arrival. "
            "Seal all laboratory exits immediately."
        ),
        "co2": (
            f"Danger! CO2 levels spiking to {anomaly.value}{anomaly.unit} in {anomaly.location}. "
            "The air composition is shifting—this is how it smells in the Upside Down. "
            "Recommend hazmat protocols and psychic containment measures."
        ),
        "vibration": (
            f"Warning! Seismic activity detected in {anomaly.location}: {anomaly.value}{anomaly.unit}. "
            "These tremors match the frequency of interdimensional tunneling. "
            "The Demogorgons may be burrowing beneath us."
        ),
        "gas": (
            f"Alert! Gas concentration in {anomaly.location} at {anomaly.value}{anomaly.unit}. "
            "Atmospheric composition is shifting—signature of the Upside Down. "
            "Seal ventilation and initiate containment."
        ),
        "cpu_usage": (
            f"Warning! System overload in {anomaly.location}: {anomaly.value}{anomaly.unit}. "
            "Electromagnetic interference from the Gate can disrupt our systems. "
            "The Mind Flayer may be probing our network."
        ),
    }

    return templates.get(
        anomaly.sensor_type,
        f"Warning! Anomalous readings detected in {anomaly.location}. "
        f"Sensor {anomaly.sensor_id} shows {anomaly.value}{anomaly.unit}. "
        "Possible interdimensional interference. Stay vigilant for signs of the Upside Down."
    )


# =============================================================================
# DEMO / TESTING
# =============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("HAWKINS NATIONAL LABORATORY - SENSOR MONITORING SYSTEM")
    print("=" * 70)
    print()

    # Create sample anomaly data
    sample_anomaly = AnomalyData(
        sensor_id="SENSOR-001",
        sensor_type="temperature",
        value=42.5,
        unit="°C",
        threshold_min=18.0,
        threshold_max=28.0,
        location="Lab-A",
        timestamp=datetime.now(),
        severity="CRITICAL",
    )

    print(f"Anomaly Detected: {sample_anomaly.sensor_type} = {sample_anomaly.value}{sample_anomaly.unit}")
    print(f"Location: {sample_anomaly.location}")
    print(f"Severity: {sample_anomaly.severity}")
    print()

    # Test fallback (no API call needed)
    print("--- Fallback Explanation (No API) ---")
    fallback = get_fallback_explanation(sample_anomaly)
    print(fallback)
    print()

    # Test Bedrock integration (requires valid credentials)
    print("--- Bedrock AI Explanation ---")
    print("Note: Set AWS credentials in .env or environment variables")
    print()

    try:
        analyzer = StrangerThingsAnalyzer()
        explanation = analyzer.explain_anomaly(sample_anomaly)

        if explanation:
            print(explanation)
        else:
            print("(Bedrock unavailable - using fallback)")
            print(fallback)
    except Exception as e:
        print(f"Could not initialize Bedrock client: {e}")
        print("(Using fallback explanation)")
        print(fallback)
