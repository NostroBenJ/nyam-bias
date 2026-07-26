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

# Model for the morning brief and the in-app chat.
# claude-opus-5 is the current flagship. claude-sonnet-5 is cheaper and still
# strong; claude-haiku-4-5 is the cheapest if you only want the templated-brief
# upgrade. A morning brief is a small prompt and a short output either way.
CLAUDE_MODEL = os.getenv("NYAM_CLAUDE_MODEL", "claude-opus-5")

# How many turns of chat history to keep. The snapshot is re-injected fresh on
# every turn, so old turns only carry the conversation, not stale market data.
CHAT_MAX_TURNS = 20

# ----------------------------------------------------------------------------
# MARKET / TICKERS
# ----------------------------------------------------------------------------
# The default underlying the dashboard opens on. Changed at runtime from the
# ticker selector in the top-left; this is only the starting value.
PRIMARY_TICKER = os.getenv("NYAM_TICKER", "SPY")

# What the selector offers. Add anything with a liquid option chain.
TICKERS = ["SPY", "QQQ", "IWM", "NVDA", "TSLA", "AAPL", "AMZN", "META", "MSFT", "GOOGL"]

# SMT divergence needs a CONFIRMER: a correlated instrument that should be
# making the same highs/lows. When one index makes a new overnight extreme and
# the other doesn't, that non-confirmation often front-runs a reversal.
# SPY<->QQQ is the ES/NQ proxy pair. Single names confirm against their index.
SMT_CONFIRMER = {"SPY": "QQQ", "QQQ": "SPY", "IWM": "SPY"}
SMT_DEFAULT_CONFIRMER = "SPY"   # single names (NVDA, TSLA, ...) confirm vs SPY


def confirmer_for(ticker: str) -> str:
    """The SMT partner for `ticker`. Never returns the ticker itself."""
    c = SMT_CONFIRMER.get(ticker.upper(), SMT_DEFAULT_CONFIRMER)
    return "QQQ" if c == ticker.upper() else c


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
