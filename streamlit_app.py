"""
Hawkins Lab — Stranger Things Themed Dashboard

Interactive dashboard for sensor data, breach level, and AI explanations.
Run: streamlit run streamlit_app.py
"""

import time
import streamlit as st
import pandas as pd

from sensor_simulator import generate_sensor_data
from anomaly_detector import AnomalyDetector
from breach_correlator import compute_breach_level
from aws_bedrock_integration import (
    StrangerThingsAnalyzer,
    AnomalyData,
    get_fallback_explanation,
)
from main import anomaly_result_to_anomaly_data_list

# Page config
st.set_page_config(
    page_title="Hawkins Lab Monitor",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Themed CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&display=swap');
    .stApp { background: linear-gradient(180deg, #0d0d0d 0%, #1a1a2e 50%, #0d0d0d 100%); }
    h1, h2, h3 { color: #00ff88 !important; font-family: 'Share Tech Mono', monospace !important; }
    .breach-box { 
        border: 2px solid #00ff88; 
        border-radius: 8px; 
        padding: 1rem; 
        margin: 1rem 0;
        background: rgba(0,255,136,0.05);
        font-family: 'Share Tech Mono', monospace;
    }
    .ai-quote { 
        border-left: 4px solid #ff6b00; 
        padding-left: 1rem; 
        margin: 1rem 0;
        font-style: italic;
        color: #ccc;
    }
    .metric-card {
        background: rgba(255,255,255,0.05);
        border-radius: 8px;
        padding: 0.75rem;
        margin: 0.25rem 0;
        border: 1px solid #333;
    }
    div[data-testid="stMetricValue"] { color: #00ff88 !important; }
</style>
""", unsafe_allow_html=True)


def init_session_state():
    if "history" not in st.session_state:
        st.session_state.history = []
    if "last_reading" not in st.session_state:
        st.session_state.last_reading = None  # (data, result, breach, ai_text)
    if "detector" not in st.session_state:
        st.session_state.detector = AnomalyDetector(use_zscore=True)
    if "bedrock" not in st.session_state:
        try:
            st.session_state.bedrock = StrangerThingsAnalyzer()
        except Exception:
            st.session_state.bedrock = None
    if "max_history" not in st.session_state:
        st.session_state.max_history = 50


def take_reading(sensor_id: str, location: str):
    data = generate_sensor_data(sensor_id=sensor_id, location=location)
    detector = st.session_state.detector
    result = detector.analyze(data)
    breach = compute_breach_level(result)

    row = {
        "timestamp": data.get("timestamp", "")[:19].replace("T", " "),
        "temperature": data["readings"]["temperature"]["value"],
        "gas": data["readings"]["gas"]["value"],
        "vibration": data["readings"]["vibration"]["value"],
        "cpu_usage": data["readings"]["cpu_usage"]["value"],
        "breach_level": breach.level,
        "anomaly": result.get("anomaly_detected", False),
    }
    st.session_state.history.append(row)
    if len(st.session_state.history) > st.session_state.max_history:
        st.session_state.history.pop(0)

    ai_text = None
    if result.get("anomaly_detected") and st.session_state.bedrock:
        anomaly_list = anomaly_result_to_anomaly_data_list(result, data)
        if anomaly_list:
            try:
                ai_text = st.session_state.bedrock.explain_anomaly(anomaly_list[0])
            except Exception:
                ai_text = get_fallback_explanation(anomaly_list[0])
            if not ai_text:
                ai_text = get_fallback_explanation(anomaly_list[0])
    elif result.get("anomaly_detected"):
        anomaly_list = anomaly_result_to_anomaly_data_list(result, data)
        if anomaly_list:
            ai_text = get_fallback_explanation(anomaly_list[0])

    st.session_state.last_reading = (data, result, breach, ai_text)
    return data, result, breach, ai_text


init_session_state()

# Sidebar
st.sidebar.title("🔬 Hawkins Lab")
st.sidebar.markdown("---")
sensor_id = st.sidebar.text_input("Sensor ID", value="HAWKINS-LAB-001")
location = st.sidebar.text_input("Location", value="main_lab")
st.sidebar.markdown("---")
take_one = st.sidebar.button("📡 Take reading")
auto_refresh = st.sidebar.checkbox("Auto-refresh (every 5s)", value=False)
voice_alert = st.sidebar.checkbox("Play voice alert (MiniMax)", value=True)
st.sidebar.markdown("---")
st.sidebar.caption("Interdimensional Anomaly Detection • AWS Bedrock + Datadog")

# Main area
st.title("HAWKINS NATIONAL LABORATORY")
st.subheader("Interdimensional Anomaly Detection System")
st.markdown("---")

# Take new reading on button (or first auto-refresh)
if take_one:
    with st.spinner("Scanning for interdimensional activity..."):
        take_reading(sensor_id, location)

# Display last reading (current state)
last = st.session_state.last_reading
if last:
    data, result, breach, ai_text = last
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Temperature", f"{data['readings']['temperature']['value']} °C",
                  "⚠️ Anomaly" if data["readings"]["temperature"]["is_anomaly"] else "✓")
    with col2:
        st.metric("Gas", f"{data['readings']['gas']['value']} ppm",
                  "⚠️ Anomaly" if data["readings"]["gas"]["is_anomaly"] else "✓")
    with col3:
        st.metric("Vibration", f"{data['readings']['vibration']['value']} mm/s",
                  "⚠️ Anomaly" if data["readings"]["vibration"]["is_anomaly"] else "✓")
    with col4:
        st.metric("CPU", f"{data['readings']['cpu_usage']['value']} %",
                  "⚠️ Anomaly" if data["readings"]["cpu_usage"]["is_anomaly"] else "✓")

    st.markdown(f"""
    <div class="breach-box">
        <strong>🔮 UPSIDE DOWN BREACH LEVEL: {breach.level}/10</strong> — {breach.label}<br/>
        <small>{breach.recommendation}</small>
    </div>
    """, unsafe_allow_html=True)

    if ai_text:
        st.markdown("#### 🎬 AI Analysis (Hawkins Lab)")
        st.markdown(f'<div class="ai-quote">« {ai_text} »</div>', unsafe_allow_html=True)
        if voice_alert:
            try:
                from minimax_voice import generate_speech
                path = generate_speech(ai_text)
                if path:
                    with open(path, "rb") as f:
                        st.audio(f.read(), format="audio/mp3")
            except Exception:
                pass
else:
    st.info("👆 Click **Take reading** in the sidebar to start monitoring.")

if st.session_state.history:
    st.markdown("---")
    st.subheader("📈 Sensor history")
    df = pd.DataFrame(st.session_state.history)
    st.line_chart(
        df.set_index("timestamp")[["temperature", "gas", "vibration", "cpu_usage"]],
        height=300,
    )
    st.caption("Breach level over time")
    st.bar_chart(df.set_index("timestamp")[["breach_level"]], height=200)

# Auto-refresh: take a new reading every 5 seconds
if auto_refresh:
    time.sleep(5)
    take_reading(sensor_id, location)
    st.rerun()
