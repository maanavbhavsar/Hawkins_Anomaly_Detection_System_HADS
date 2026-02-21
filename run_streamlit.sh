#!/bin/bash
cd "$(dirname "$0")"
if [ ! -f "venv/bin/activate" ]; then
    echo "Creating venv..."
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi
streamlit run streamlit_app.py
