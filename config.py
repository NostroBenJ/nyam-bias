"""
Central configuration for the NYAM Bias Engine.

Everything you'll want to tweak lives here so you don't have to dig through
the code. Read the comments — they explain WHY each setting exists.
"""
import os
from zoneinfo import ZoneInfo

# ----------------------------------------------------------------------------
# DATA MODE
# ----------------------------------------------------------------------------
# Start in mock mode so the whole app runs with ZERO keys and ZERO cost.
# Flip to False once you've installed yfinance and want real option chains.
USE_MOCK_DATA = os.getenv("NYAM_MOCK", "1") == "1"

# If you ever want to use Claude for the written brief, set this env var:
#   export ANTHROPIC_API_KEY=sk-ant-...
# Without it, the app falls back to a templated brief built from the signals,
# so it still runs and shows you the layout. (No key = no cost.)
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")

# Cheapest-good model for a daily brief. Swap to claude-haiku-4-5-20251001 for
# even lower cost, or a claude-opus model if you want maximum reasoning quality.
CLAUDE_MODEL = os.getenv("NYAM_CLAUDE_MODEL", "claude-sonnet-4-6")

# ----------------------------------------------------------------------------
# MARKET / TICKERS
# ----------------------------------------------------------------------------
# You trade MNQ (Nasdaq) and watch ES (S&P) for SMT divergence.
# QQQ is the liquid options proxy for NQ; SPY is the proxy for ES.
PRIMARY_TICKER = "QQQ"     # drives your NQ bias
SMT_PAIR = ("QQQ", "SPY")  # cross-market divergence check (NQ vs ES proxy)

# How many expirations to roll into the GEX aggregation.
# 0DTE + near-dated dominate dealer hedging into the open, so keep this tight.
GEX_MAX_DTE = 7            # include expiries within this many days
RISK_FREE_RATE = 0.043     # ~current short rate; only affects gamma slightly

# ----------------------------------------------------------------------------
# SCHEDULE (all times America/New_York)
# ----------------------------------------------------------------------------
TZ = ZoneInfo("America/New_York")
PREMARKET_START = "07:00"   # begin auto-refreshing
MARKET_OPEN = "09:30"       # the moment your bias is for
REFRESH_SECONDS = 60        # frontend polls /api/bias this often
SNAPSHOT_AND_LOG_AT = "09:25"  # auto-write the Obsidian note 5 min before open

# ----------------------------------------------------------------------------
# OBSIDIAN
# ----------------------------------------------------------------------------
# Point this at your vault. The logger writes one markdown note per morning.
# Leave as-is to write into ./obsidian_out for testing.
OBSIDIAN_VAULT = os.getenv("NYAM_VAULT", os.path.join(os.path.dirname(__file__), "obsidian_out"))
OBSIDIAN_SUBFOLDER = "NYAM Bias"   # notes land in <vault>/<subfolder>/YYYY-MM-DD.md

# ----------------------------------------------------------------------------
# TRACK RECORD
# ----------------------------------------------------------------------------
# Where predictions + outcomes are stored (one JSON file you can open & inspect).
STORE_DIR = os.path.join(os.path.dirname(__file__), "data_store")
# A day's open->close move smaller than this (%) counts as a flat/range day,
# which is how a NEUTRAL lean gets graded correct. Tune to taste.
GRADE_BAND_PCT = 0.15
GRADE_TIME = "16:15"   # after the close, grade today's prediction (America/New_York)
