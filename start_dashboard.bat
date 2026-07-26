@echo off
REM ============================================================
REM  NYAM Bias Engine launcher
REM  Double-click to start the dashboard. Close this window to stop it.
REM
REM  Every setting lives here so you never have to edit the code.
REM ============================================================
cd /d "%~dp0"

REM --- data ---------------------------------------------------
REM 1 = offline synthetic data (no keys, no cost). 0 = real chains.
set NYAM_MOCK=0

REM Live provider: "yahoo" (free, ~15-min delayed) or "uw" (Unusual Whales —
REM real-time chains, day-over-day OI, flow alerts, dark pool).
REM Before switching to uw, check which endpoints your tier allows:
REM     py -m data.unusual_whales probe SPY
set NYAM_PROVIDER=yahoo
REM set UW_API_KEY=your-unusual-whales-key

REM Ticker the dashboard opens on (change it live in the UI, top-left).
set NYAM_TICKER=SPY

REM --- optional: Claude brief + in-app chat -------------------
REM Without a key the brief falls back to a template and chat stays disabled.
REM set ANTHROPIC_API_KEY=sk-ant-...

REM --- optional: your Obsidian vault --------------------------
REM Without this, notes land in .\obsidian_out instead of your real vault.
REM set NYAM_VAULT=C:\path\to\your\Obsidian Vault

echo Starting NYAM Bias Engine...
echo   mock=%NYAM_MOCK%  provider=%NYAM_PROVIDER%  ticker=%NYAM_TICKER%
echo   http://127.0.0.1:8000
echo Close this window when you're done.
echo.
start "" /b cmd /c "timeout /t 3 >nul & start http://127.0.0.1:8000"
py app.py
pause
