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


def get_market() -> dict:
    if config.USE_MOCK_DATA:
        return mock_market()
    return _live_market()


# ----------------------------------------------------------------------------
# LIVE  (free, ~15-min delayed — fine for a pre-market bias)
# ----------------------------------------------------------------------------
def _live_market() -> dict:
    import yfinance as yf

    primary = _live_ticker(yf, config.SMT_PAIR[0], with_chain=True)
    secondary = _live_ticker(yf, config.SMT_PAIR[1], with_chain=False)
    return {
        "primary": primary,
        "secondary": secondary,
        "news": _live_news(yf, config.SMT_PAIR[0]),
    }


def _live_ticker(yf, symbol: str, with_chain: bool) -> dict:
    tk = yf.Ticker(symbol)
    hist = tk.history(period="5d", interval="1d")
    spot = float(hist["Close"].iloc[-1])
    prior = hist.iloc[-2]
    # Overnight range: use the most recent pre/post extended-hours bars if
    # available, otherwise fall back to the prior day's range as a placeholder.
    on = tk.history(period="1d", interval="5m", prepost=True)
    on_high = float(on["High"].max()) if len(on) else float(prior["High"])
    on_low = float(on["Low"].min()) if len(on) else float(prior["Low"])

    out = {
        "ticker": symbol,
        "spot": round(spot, 2),
        "prior_high": round(float(prior["High"]), 2),
        "prior_low": round(float(prior["Low"]), 2),
        "prior_close": round(float(prior["Close"]), 2),
        "on_high": round(on_high, 2),
        "on_low": round(on_low, 2),
    }
    if with_chain:
        out["expiries"] = _live_expiries(tk)
        out["nq_price"] = _nq_price(yf, spot)
    return out


def _nq_price(yf, qqq_spot: float) -> float:
    """Live NQ (E-mini Nasdaq) front-month price for the QQQ->NQ ratio.
    Futures data on Yahoo can be flaky, so fall back to ~41x if it fails —
    that keeps the conversion working instead of crashing the app."""
    try:
        h = yf.Ticker("NQ=F").history(period="1d")
        if len(h):
            return float(h["Close"].iloc[-1])
    except Exception:
        pass
    return round(qqq_spot * 41.0, 2)


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
