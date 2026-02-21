"""
Hawkins Lab — Stranger Things Themed Dashboard

Interactive dashboard for sensor data, breach level, and AI explanations.
Run: streamlit run streamlit_app.py
"""

import os
import time
import streamlit as st
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

from sensor_simulator import generate_sensor_data
from anomaly_detector import AnomalyDetector
from breach_correlator import compute_breach_level
from aws_bedrock_integration import (
    StrangerThingsAnalyzer,
    AnomalyData,
    get_fallback_explanation,
)
from main import anomaly_result_to_anomaly_data_list

# Datadog dashboard URLs — embed URLs from Share → Embed (referrer e.g. http://localhost:8501 must be allowlisted)
_DD_LAB_SENSORS = os.getenv("DD_EMBED_LAB_SENSORS", "https://p.datadoghq.com/sb/embed/bfdb63b2-0c07-11f1-831f-929eff2735cf-f78f691e60991913f7b34a4dc044b50a")
_DD_BREACH_LEVEL = os.getenv("DD_EMBED_BREACH_LEVEL", "https://p.datadoghq.com/sb/embed/bfdb63b2-0c07-11f1-831f-929eff2735cf-a96aa6b105a2d4e0d4c06c3356c7ae40")
_DD_ANOMALY_EVENTS = os.getenv("DD_EMBED_ANOMALY_EVENTS", "https://p.datadoghq.com/sb/embed/bfdb63b2-0c07-11f1-831f-929eff2735cf-fd7e0c5488bcba70196a198d717dc6bc")

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
    if "sticky_alert" not in st.session_state:
        st.session_state.sticky_alert = None  # (data, result, breach, ai_text, audio_b64) or None; stays until dismissed
    if "detector" not in st.session_state:
        st.session_state.detector = AnomalyDetector(use_zscore=True)
    if "bedrock" not in st.session_state:
        try:
            st.session_state.bedrock = StrangerThingsAnalyzer()
        except Exception:
            st.session_state.bedrock = None
    if "max_history" not in st.session_state:
        st.session_state.max_history = 50


def take_reading(sensor_id: str, location: str, voice_alert: bool = True):
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
    # Set sticky alert on first anomaly so it stays until user acknowledges
    if result.get("anomaly_detected") and st.session_state.sticky_alert is None:
        audio_b64 = None
        if voice_alert and ai_text:
            try:
                import base64
                from minimax_voice import generate_speech, build_voice_alert_text
                voice_text = build_voice_alert_text()
                path = generate_speech(voice_text)
                if path:
                    with open(path, "rb") as f:
                        audio_b64 = base64.b64encode(f.read()).decode()
            except Exception:
                pass
        st.session_state.sticky_alert = (data, result, breach, ai_text, audio_b64)
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
st.sidebar.markdown("### 📊 Datadog")
st.sidebar.caption("Dashboards are embedded below. Open in new tab:")
st.sidebar.markdown(
    f'<a href="{_DD_LAB_SENSORS}" target="_blank" rel="noopener">Lab Sensors</a> · '
    f'<a href="{_DD_BREACH_LEVEL}" target="_blank" rel="noopener">Breach</a> · '
    f'<a href="{_DD_ANOMALY_EVENTS}" target="_blank" rel="noopener">Anomaly</a>',
    unsafe_allow_html=True,
)
with st.sidebar.expander("Datadog anomaly monitor"):
    st.caption(
        "This app sends raw metrics (lab.sensor.*) to Datadog. To use Datadog's native anomaly detection: "
        "Monitors → New Monitor → Metric → e.g. avg:lab.sensor.temperature → Detection: Anomaly → Save."
    )
    st.markdown(
        '<a href="https://app.datadoghq.com/monitors/create" target="_blank" rel="noopener">Create monitor</a>',
        unsafe_allow_html=True,
    )
st.sidebar.markdown("---")
st.sidebar.caption("Interdimensional Anomaly Detection • AWS Bedrock + Datadog")

# Main area
st.title("HAWKINS NATIONAL LABORATORY")
st.subheader("Interdimensional Anomaly Detection System")
st.markdown("---")

# Take new reading on button (or first auto-refresh)
if take_one:
    with st.spinner("Scanning for interdimensional activity..."):
        take_reading(sensor_id, location, voice_alert=voice_alert)

# Display last reading: sensor metrics always from current reading
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

    # Alert block: show sticky alert until acknowledged, else show current reading's breach/AI/audio
    sticky = st.session_state.get("sticky_alert")
    if sticky:
        _data, _result, _breach, _ai_text, _audio_b64 = sticky
        st.markdown(f"""
        <div class="breach-box">
            <strong>🔮 UPSIDE DOWN BREACH LEVEL: {_breach.level}/10</strong> — {_breach.label}<br/>
            <small>{_breach.recommendation}</small>
        </div>
        """, unsafe_allow_html=True)
        st.markdown("#### 🎬 AI Analysis (Hawkins Lab)")
        st.markdown(f'<div class="ai-quote">« {_ai_text} »</div>', unsafe_allow_html=True)
        if _audio_b64:
            st.markdown(
                f'<audio controls><source src="data:audio/mp3;base64,{_audio_b64}" type="audio/mp3"></audio>',
                unsafe_allow_html=True,
            )
        if st.button("Acknowledge", key="dismiss_alert", type="primary"):
            st.session_state.sticky_alert = None
            st.rerun()
    else:
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
                    import base64
                    from minimax_voice import generate_speech, build_voice_alert_text
                    voice_text = build_voice_alert_text()
                    path = generate_speech(voice_text)
                    if path:
                        with open(path, "rb") as f:
                            audio_bytes = f.read()
                        b64 = base64.b64encode(audio_bytes).decode()
                        st.markdown(
                            f'<audio autoplay controls><source src="data:audio/mp3;base64,{b64}" type="audio/mp3"></audio>',
                            unsafe_allow_html=True,
                        )
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

# Embedded Datadog dashboards (referrer must be allowlisted in Datadog Share → Embed, e.g. http://localhost:8501/)
st.markdown("---")
st.subheader("📊 Datadog dashboards")
tab1, tab2, tab3 = st.tabs(["Lab Sensor Monitoring", "Breach Level", "Anomaly events"])
_EMBED_HEIGHT = 620


def _embed_dashboard(url: str, height: int = _EMBED_HEIGHT) -> None:
    if not url or not url.startswith("http"):
        st.warning("Dashboard URL not configured. Set DD_EMBED_* in .env if using embed URLs.")
        return
    html = f'<iframe src="{url}" width="100%" height="{height}" frameborder="0" allow="fullscreen" style="border-radius:8px;"></iframe>'
    st.components.v1.html(html, height=height, scrolling=True)


with tab1:
    _embed_dashboard(_DD_LAB_SENSORS)
with tab2:
    _embed_dashboard(_DD_BREACH_LEVEL)
with tab3:
    _embed_dashboard(_DD_ANOMALY_EVENTS)

# Auto-refresh: take a new reading every 5 seconds (sensor metrics update; sticky alert stays until acknowledged)
if auto_refresh:
    time.sleep(5)
    take_reading(sensor_id, location, voice_alert=voice_alert)
    st.rerun()
