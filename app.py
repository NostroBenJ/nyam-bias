"""
app.py  --  The desktop app. Run it and open http://127.0.0.1:8000

It does three things:
  1. Serves the dark dashboard at /
  2. Exposes the live bias snapshot at /api/bias (the frontend polls this)
  3. Runs a background scheduler that refreshes through the pre-market window
     and auto-writes the Obsidian note shortly before the open.

Run:
    pip install -r requirements.txt
    python app.py
"""
import datetime as dt
import threading

import uvicorn
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

import config
from pipeline import build_snapshot
from logging_obsidian import log_to_obsidian
from analysis import tracker
from data.data_sources import get_ohlc

app = FastAPI(title="NYAM Bias Engine")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Cache the latest snapshot PER TICKER so the UI and the logger share one
# source of truth. Keyed by ticker because switching the selector must not
# hand you another symbol's stale GEX while the new pull is in flight.
_latest = {}              # ticker -> snapshot
_running = {"on": True}   # live-feed toggle (the Start/Stop buttons)
_active = {"ticker": config.PRIMARY_TICKER}   # what the scheduler refreshes
_lock = threading.Lock()


def refresh(ticker: str = None):
    ticker = (ticker or _active["ticker"]).upper()
    snap = build_snapshot(ticker)
    tracker.record_prediction(snap)   # saves once per day per ticker
    with _lock:
        _latest[ticker] = snap
    return snap


def scheduled_refresh():
    """The auto-refresh job — only pulls when the live feed is running."""
    if _running["on"]:
        refresh()


def scheduled_log():
    """Called once each morning to persist the note to Obsidian."""
    snap = refresh()
    path = log_to_obsidian(snap)
    print(f"[{dt.datetime.now(config.TZ)}] Logged NYAM bias -> {path}")


@app.get("/")
def index():
    return FileResponse("templates/dashboard.html")


@app.get("/api/tickers")
def api_tickers():
    """Populates the selector in the top-left."""
    return {"tickers": config.TICKERS, "active": _active["ticker"]}


@app.get("/api/bias")
def api_bias(ticker: str = None):
    t = (ticker or _active["ticker"]).upper()
    with _lock:
        data = _latest.get(t)
    if data is None:
        data = refresh(t)
    return JSONResponse(data)


@app.post("/api/ticker")
def api_ticker(ticker: str):
    """Switch the active underlying. Makes it the scheduler's target too, so
    the auto-refresh follows what you're actually looking at."""
    t = ticker.upper()
    if t not in config.TICKERS:
        config.TICKERS.append(t)      # allow ad-hoc symbols from the selector
    _active["ticker"] = t
    return JSONResponse(refresh(t))


@app.post("/api/refresh")
def api_refresh(ticker: str = None):
    """Force an immediate fresh pull (the manual Refresh button)."""
    return JSONResponse(refresh(ticker))


@app.post("/api/start")
def api_start(ticker: str = None):
    """Resume the live feed and pull fresh data immediately."""
    _running["on"] = True
    return JSONResponse(refresh(ticker))


@app.post("/api/stop")
def api_stop():
    """Pause the live feed (stops pulling from the data source)."""
    _running["on"] = False
    return {"running": False}


@app.get("/api/status")
def api_status():
    return {"running": _running["on"], "ticker": _active["ticker"]}


@app.post("/api/log")
def api_log():
    """Manual 'log now' button hook."""
    scheduled_log()
    return {"status": "logged"}


def start_scheduler():
    sched = BackgroundScheduler(timezone=str(config.TZ))
    # Refresh through the pre-market window ONLY, weekdays only.
    # This was an "interval" job anchored to a start_date earlier the same day:
    # with the anchor already in the past, APScheduler just steps forward to
    # now, so it polled around the clock every day including weekends instead
    # of during the window it was meant to cover.
    start_h, start_m = map(int, config.PREMARKET_START.split(":"))
    open_h, open_m = map(int, config.MARKET_OPEN.split(":"))
    every = max(config.REFRESH_SECONDS, 30)
    sched.add_job(scheduled_refresh, "cron", day_of_week="mon-fri",
                  hour=f"{start_h}-{open_h}", second=f"*/{every}" if every < 60 else "0",
                  minute="*" if every < 60 else f"*/{max(1, every // 60)}")
    # auto-log shortly before the open
    log_h, log_m = map(int, config.SNAPSHOT_AND_LOG_AT.split(":"))
    sched.add_job(scheduled_log, "cron", hour=log_h, minute=log_m,
                  day_of_week="mon-fri")
    # grade yesterday's call after today's close
    grade_h, grade_m = map(int, config.GRADE_TIME.split(":"))
    sched.add_job(lambda: tracker.grade_pending(get_ohlc), "cron", hour=grade_h, minute=grade_m,
                  day_of_week="mon-fri")
    sched.start()


if __name__ == "__main__":
    tracker.ensure_seeded()              # mock demo history
    tracker.grade_pending(get_ohlc)      # grade any past, ungraded calls
    refresh()            # warm the cache so the first page load is instant
    start_scheduler()
    print("NYAM Bias Engine running at http://127.0.0.1:8000  (mock=%s)" % config.USE_MOCK_DATA)
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")
