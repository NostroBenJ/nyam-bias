"""
pipeline.py  --  Runs the whole chain into one snapshot dict the dashboard
and the Obsidian logger both consume.
   raw data -> per-expiry GEX + aggregate GEX -> derived reads -> bias -> brief
"""
import datetime as dt

import config
from analysis import gex as gex_mod
from analysis import levels as levels_mod
from analysis import smt as smt_mod
from analysis import bias_engine
from analysis import derived
from analysis import tracker
import store
from data.data_sources import get_market
from claude_brief import generate_brief


def build_snapshot(ticker: str = None) -> dict:
    market = get_market(ticker)
    p, s = market["primary"], market["secondary"]
    r = config.RISK_FREE_RATE
    expiries = p["expiries"]

    # --- aggregate GEX across all loaded expirations -----------------------
    merged = {"calls": [], "puts": []}
    for e in expiries:
        merged["calls"] += e["calls"]
        merged["puts"] += e["puts"]
    gex = gex_mod.compute_gex(merged, p["spot"], r)

    # --- per-expiry GEX (for confluence) -----------------------------------
    per_expiry = [
        {"label": e["label"], "gex": gex_mod.compute_gex({"calls": e["calls"], "puts": e["puts"]}, p["spot"], r)}
        for e in expiries
    ]
    front_dte = min(e["dte"] for e in expiries)

    # --- derived reads ------------------------------------------------------
    em = derived.expected_move(p["spot"], gex["atm_iv"], front_dte)
    expiry_conf = derived.multi_expiry_confluence(per_expiry)
    level_map = derived.build_level_map(gex)
    neg_zone = derived.neg_gamma_zone(gex)

    # --- session levels + cross-market -------------------------------------
    levels = levels_mod.session_levels({
        "prior_high": p["prior_high"], "prior_low": p["prior_low"],
        "prior_close": p["prior_close"], "on_high": p["on_high"],
        "on_low": p["on_low"], "spot": p["spot"],
    })
    confluences = levels_mod.find_confluences(levels, gex)
    smt = smt_mod.smt_divergence(
        {"name": p["ticker"], "on_high": p["on_high"], "on_low": p["on_low"],
         "prior_high": p["prior_high"], "prior_low": p["prior_low"], "spot": p["spot"],
         "on_is_real": p.get("on_is_real", True)},
        {"name": s["ticker"], "on_high": s["on_high"], "on_low": s["on_low"],
         "prior_high": s["prior_high"], "prior_low": s["prior_low"], "spot": s["spot"],
         "on_is_real": s.get("on_is_real", True)},
    )

    bias = bias_engine.build_bias(gex, levels, smt, market["news"], em=em, neg_zone=neg_zone)
    brief = generate_brief(bias, gex, levels, smt, market["news"])

    tracker.ensure_seeded()                       # mock-only demo history
    # stats are per-ticker: a SPY hit rate says nothing about NVDA
    track = tracker.compute_stats(store.load(), ticker=p["ticker"])

    return {
        "generated_at": dt.datetime.now(config.TZ).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "ticker": p["ticker"],
        "confirmer": s["ticker"],
        "tickers": config.TICKERS,
        "mock": config.USE_MOCK_DATA,
        "expiries_loaded": len(expiries),
        "gex": gex,
        "expected_move": em,
        "level_map": level_map,
        "neg_zone": neg_zone,
        "levels": levels,
        "confluences": confluences,
        "expiry_confluence": expiry_conf,
        "smt": smt,
        "bias": bias,
        "brief": brief,
        "news": market["news"],
        "track": track,
    }
