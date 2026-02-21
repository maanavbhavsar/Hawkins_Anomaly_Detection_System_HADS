"""
MiniMax Text-to-Speech voice alerts for Hawkins Lab.
Plays the anomaly explanation (or a short alert) when an anomaly is detected.
Set in .env: MINIMAX_API_KEY, MINIMAX_GROUP_ID. Optional: ENABLE_VOICE_ALERT=true
"""
import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "")
MINIMAX_GROUP_ID = os.getenv("MINIMAX_GROUP_ID", "")
ENABLE_VOICE_ALERT = os.getenv("ENABLE_VOICE_ALERT", "true").lower() == "true"
# TTS speaks only this phrase (no explanation). Set to "Warning! Warning! Warning!" for the other option.
VOICE_ALERT_PHRASE = os.getenv("VOICE_ALERT_PREFIX", "Alert! Alert! Alert!").strip() or "Alert! Alert! Alert!"
T2A_URL = "https://api.minimax.io/v1/t2a_v2"


def build_voice_alert_text(full_explanation: str = "") -> str:
    """
    Return the voice alert phrase only: "Alert! Alert! Alert!" or "Warning! Warning! Warning!" (no extra text).
    """
    return VOICE_ALERT_PHRASE


def _call_minimax_t2a(text: str) -> bytes | None:
    """Call MiniMax T2A API; return raw MP3 bytes or None."""
    if not MINIMAX_API_KEY or not MINIMAX_GROUP_ID or not text.strip():
        return None
    try:
        import requests
    except ImportError:
        print("[Voice] Install requests: pip install requests")
        return None
    # Cap length for alert (API limit 10k; we want short for speed)
    text = text.strip()[:1500]
    payload = {
        "model": "speech-2.8-turbo",
        "group_id": MINIMAX_GROUP_ID,
        "text": text,
        "stream": False,
        "output_format": "hex",
        "language_boost": "English",
        "voice_setting": {
            "voice_id": "English_expressive_narrator",
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
            "channel": 1,
        },
    }
    headers = {
        "Authorization": f"Bearer {MINIMAX_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        r = requests.post(T2A_URL, json=payload, headers=headers, timeout=30)
        r.raise_for_status()
        data = r.json()
        base = data.get("base_resp", {})
        if base.get("status_code") != 0:
            return None
        audio_hex = (data.get("data") or {}).get("audio")
        if not audio_hex:
            return None
        return bytes.fromhex(audio_hex)
    except Exception as e:
        print(f"[Voice] MiniMax T2A error: {e}")
        return None


def generate_speech(text: str) -> str | None:
    """
    Convert text to speech via MiniMax; save to a temp file.
    Returns path to the temp MP3 file, or None on failure.
    """
    if not ENABLE_VOICE_ALERT or not MINIMAX_API_KEY or not MINIMAX_GROUP_ID:
        return None
    raw = _call_minimax_t2a(text)
    if not raw:
        return None
    fd, path = tempfile.mkstemp(suffix=".mp3")
    try:
        os.write(fd, raw)
        os.close(fd)
        return path
    except Exception:
        try:
            os.close(fd)
        except Exception:
            pass
        return None


def speak_alert(text: str) -> bool:
    """
    Generate speech from text and play it (CLI: opens default player).
    Returns True if played, False otherwise.
    """
    path = generate_speech(text)
    if not path:
        return False
    try:
        if os.name == "nt":
            os.startfile(path)
        else:
            import subprocess
            subprocess.run(["xdg-open", path], check=False, timeout=2)
        return True
    except Exception as e:
        print(f"[Voice] Playback error: {e}")
        return False
