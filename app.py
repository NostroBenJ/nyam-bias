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

# cache the latest snapshot so the UI and the logger share one source of truth
_latest = {"data": None}
_running = {"on": True}   # live-feed toggle (the Start/Stop buttons)
_lock = threading.Lock()


def refresh():
    snap = build_snapshot()
    tracker.record_prediction(snap)   # saves once per day; never overwrites
    with _lock:
        _latest["data"] = snap
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


@app.get("/api/bias")
def api_bias():
    with _lock:
        data = _latest["data"]
    if data is None:
        data = refresh()
    return JSONResponse(data)


@app.post("/api/refresh")
def api_refresh():
    """Force an immediate fresh pull (the manual Refresh button)."""
    return JSONResponse(refresh())


@app.post("/api/start")
def api_start():
    """Resume the live feed and pull fresh data immediately."""
    _running["on"] = True
    return JSONResponse(refresh())


@app.post("/api/stop")
def api_stop():
    """Pause the live feed (stops pulling from the data source)."""
    _running["on"] = False
    return {"running": False}


@app.get("/api/status")
def api_status():
    return {"running": _running["on"]}


@app.post("/api/log")
def api_log():
    """Manual 'log now' button hook."""
    scheduled_log()
    return {"status": "logged"}


def start_scheduler():
    sched = BackgroundScheduler(timezone=str(config.TZ))
    # refresh through the pre-market window
    start_h, start_m = map(int, config.PREMARKET_START.split(":"))
    open_h, open_m = map(int, config.MARKET_OPEN.split(":"))
    sched.add_job(scheduled_refresh, "interval", seconds=max(config.REFRESH_SECONDS, 30),
                  start_date=dt.datetime.now(config.TZ).replace(hour=start_h, minute=start_m, second=0))
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
