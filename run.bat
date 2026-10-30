@echo off
cd /d "%~dp0"
python -m streamlit run app.py
echo.
echo Press any key to exit...
pause >nul
