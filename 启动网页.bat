@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Starting Job Matcher Web UI...
python web_app.py
pause
