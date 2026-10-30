@echo off
cd /d "%~dp0"
python -m investment_tracker.server --open
pause
