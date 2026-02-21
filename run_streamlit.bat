@echo off
cd /d "%~dp0"
if not exist "venv\Scripts\activate.bat" (
    echo Creating venv...
    python -m venv venv
    call venv\Scripts\pip.exe install -r requirements.txt
)
call venv\Scripts\activate.bat
streamlit run streamlit_app.py
