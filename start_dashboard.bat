@echo off
REM ============================================================
REM  NYAM Bias Engine launcher
REM  Double-click this file to start the dashboard. No terminal
REM  typing needed. To shut it down, just close this window.
REM ============================================================
cd /d "%~dp0"
set NYAM_MOCK=0
echo Starting NYAM Bias Engine (live data)...
echo Your browser will open at http://127.0.0.1:8000
echo Close this window when you're done to stop it.
echo.
REM open the dashboard in the default browser after a short delay
start "" /b cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000"
py app.py
pause
