"""
data_sources.py  --  The ONLY file that touches the outside world.

In mock mode it returns synthetic data (free, offline). In live mode it pulls
free option chains from Yahoo Finance via yfinance and reshapes them into the
exact same structure the analysis code expects. Because everything downstream
reads the same shape, you can swap data providers here without touching the
GEX math, the bias engine, or the UI.

To go live:
    pip install yfinance
    export NYAM_MOCK=0
"""
import datetime as dt

import config
from data.mock_data import mock_market


def get_ohlc(ticker: str, date_iso: str) -> dict | None:
    """Fetch a single past day's OHLC for grading. None in mock mode (the
    mock store ships pre-graded)."""
    if config.USE_MOCK_DATA:
        return None
    import yfinance as yf
    d = dt.date.fromisoformat(date_iso)
    h = yf.Ticker(ticker).history(start=d.isoformat(), end=(d + dt.timedelta(days=1)).isoformat())
    if len(h) == 0:
        return None
    return {"open": float(h["Open"].iloc[0]), "close": float(h["Close"].iloc[0]),
            "high": float(h["High"].iloc[0]), "low": float(h["Low"].iloc[0])}


def get_market(ticker: str = None) -> dict:
    ticker = (ticker or config.PRIMARY_TICKER).upper()
    if config.USE_MOCK_DATA:
        return mock_market(ticker)
    return _live_market(ticker)


# ----------------------------------------------------------------------------
# LIVE  (free, ~15-min delayed — fine for a pre-market bias)
# ----------------------------------------------------------------------------
def _live_market(ticker: str) -> dict:
    import yfinance as yf

    confirmer = config.confirmer_for(ticker)
    primary = _live_ticker(yf, ticker, with_chain=True)
    secondary = _live_ticker(yf, confirmer, with_chain=False)
    return {
        "primary": primary,
        "secondary": secondary,
        "news": _live_news(yf, ticker),
    }


def _live_ticker(yf, symbol: str, with_chain: bool) -> dict:
    tk = yf.Ticker(symbol)
    hist = tk.history(period="10d", interval="1d")
    spot = float(hist["Close"].iloc[-1])

    # "Prior session" must be the last COMPLETED regular session. Whether the
    # current day already has a daily bar depends on the time of day you run
    # this, so indexing a fixed iloc[-2] silently shifts the reference day by
    # one during pre-market -- exactly when this tool is meant to be used.
    today = dt.date.today()
    last_idx = hist.index[-1].date()
    prior = hist.iloc[-2] if last_idx >= today else hist.iloc[-1]

    on_high, on_low, on_is_real = _overnight_range(tk, prior)

    out = {
        "ticker": symbol,
        "spot": round(spot, 2),
        "prior_high": round(float(prior["High"]), 2),
        "prior_low": round(float(prior["Low"]), 2),
        "prior_close": round(float(prior["Close"]), 2),
        "on_high": round(on_high, 2),
        "on_low": round(on_low, 2),
        # False => no overnight session yet; prior-day range is standing in and
        # SMT should not be read as a real divergence signal.
        "on_is_real": on_is_real,
    }
    if with_chain:
        out["expiries"] = _live_expiries(tk)
    return out


def _overnight_range(tk, prior) -> tuple:
    """
    True overnight (Globex) range: prior session's 16:00 ET close through now.

    Two things this has to get right, both of which were wrong before:

    1. WINDOW. `period="1d"` returns the last trading day 04:00-20:00 — that is
       a full regular session, not an overnight. Feeding that into SMT compares
       yesterday's day range against yesterday's day range. The overnight that
       matters for the next open starts at the PRIOR close.
    2. BAD TICKS. Yahoo's extended-hours bars include zero-volume prints with
       nonsense lows (an observed QQQ bar: O 684.85 / C 684.76 / L 649.28, vol
       0). One of those drags the overnight low 5% below reality and poisons
       every level and divergence read downstream. Zero-volume bars are dropped.

    Returns (high, low, is_real). `is_real` is False when no overnight session
    exists yet (weekends, or before the first post-close print), in which case
    the prior session's range stands in. Never widen the fallback beyond that:
    reporting a multi-day range as "overnight" invents a breakout that never
    happened and hands SMT a fake divergence.
    """
    fallback = (float(prior["High"]), float(prior["Low"]), False)
    try:
        bars = tk.history(period="5d", interval="5m", prepost=True)
    except Exception:
        return fallback
    if bars is None or len(bars) == 0:
        return fallback

    bars = bars[bars["Volume"] > 0]           # drop phantom prints
    if len(bars) == 0:
        return fallback

    # anchor at the close of the last completed regular session
    idx = bars.index
    rth_close = idx[(idx.hour == 15) & (idx.minute >= 55)]
    if not len(rth_close):
        return fallback
    on = bars[idx > rth_close[-1]]
    if not len(on):
        return fallback
    return float(on["High"].max()), float(on["Low"].min()), True


def _live_expiries(tk) -> list:
    """Return a list of per-expiration chains shaped for compute_gex()."""
    today = dt.date.today()
    expiries = []
    for exp in tk.options:
        exp_date = dt.date.fromisoformat(exp)
        dte = (exp_date - today).days
        if dte < 0 or dte > config.GEX_MAX_DTE:
            continue
        t_years = max(dte, 0.5) / 365.0
        oc = tk.option_chain(exp)
        calls, puts = [], []
        for df, bucket in ((oc.calls, calls), (oc.puts, puts)):
            for _, row in df.iterrows():
                iv = float(row.get("impliedVolatility", 0) or 0)
                oi = float(row.get("openInterest", 0) or 0)
                if iv <= 0 or oi <= 0:
                    continue
                bucket.append({
                    "strike": float(row["strike"]),
                    "oi": oi,
                    "iv": iv,
                    "t_years": t_years,
                    # yfinance snapshots have no day-over-day OI; persist daily
                    # snapshots yourself to fill this in (see README TODO).
                    "oi_change": 0,
                })
        expiries.append({"label": exp, "dte": dte, "calls": calls, "puts": puts})
    return expiries


def _live_news(yf, symbol: str) -> dict:
    """Lightweight free news pull. Econ-calendar wiring is a README TODO."""
    try:
        items = yf.Ticker(symbol).news or []
    except Exception:
        items = []
    headlines = [{"time": "", "event": n.get("title", ""), "impact": "unknown"} for n in items[:5]]
    return {"high_impact": False, "headline": headlines[0]["event"] if headlines else "", "items": headlines}
