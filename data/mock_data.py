"""
mock_data.py  --  Realistic synthetic data so the app runs with no keys, no
network, no cost. Now serves MULTIPLE expirations so the multi-expiry
confluence feature has something to chew on.
"""
import random

random.seed(7)


def _build_chain(spot: float, dte: int, wall_bias: float = 0.0):
    """Synthetic calls/puts for one expiration."""
    calls, puts = [], []
    step = round(spot * 0.0025, 0) or 1
    t_years = max(dte, 0.5) / 365.0
    for i in range(-25, 26):
        strike = round(spot + i * step, 0)
        moneyness = abs(strike - spot) / spot
        iv = 0.16 + moneyness * 1.5
        call_oi = max(0, int(9000 * (1 - (i - wall_bias) / 30)) + random.randint(-600, 600)) if i >= -5 else random.randint(200, 1500)
        put_oi = max(0, int(9000 * (1 + (i + wall_bias) / 30)) + random.randint(-600, 600)) if i <= 5 else random.randint(200, 1500)
        calls.append({"strike": strike, "oi": call_oi, "iv": iv, "t_years": t_years, "oi_change": random.randint(-400, 900)})
        puts.append({"strike": strike, "oi": put_oi, "iv": iv, "t_years": t_years, "oi_change": random.randint(-400, 1200)})
    return {"calls": calls, "puts": puts}


def mock_market():
    random.seed(7)
    qqq_spot, spy_spot = 707.00, 745.00
    # 5 expirations; walls mostly agree (high confluence) with slight variation
    expiry_specs = [
        ("Fri Jun 5", 0, 0.0),
        ("Mon Jun 8", 3, 0.0),
        ("Wed Jun 10", 5, 1.0),
        ("Fri Jun 12", 7, 0.0),
        ("Fri Jun 19", 14, -1.0),
    ]
    expiries = []
    for label, dte, bias in expiry_specs:
        ch = _build_chain(qqq_spot, dte, bias)
        expiries.append({"label": label, "dte": dte, "calls": ch["calls"], "puts": ch["puts"]})

    return {
        "primary": {
            "ticker": "QQQ",
            "spot": qqq_spot,
            "nq_price": round(qqq_spot * 40.96, 2),   # NQ (MNQ) ~= QQQ x ~41
            "expiries": expiries,
            "prior_high": 708.20, "prior_low": 702.50, "prior_close": 706.10,
            "on_high": 709.10, "on_low": 704.00, "on_is_real": True,
        },
        "secondary": {
            "ticker": "SPY",
            "spot": spy_spot,
            "prior_high": 746.50, "prior_low": 742.00, "prior_close": 745.10,
            "on_high": 745.90, "on_low": 743.00, "on_is_real": True,
        },
        "news": {
            "high_impact": True,
            "headline": "10:00 ET — ISM Services PMI",
            "items": [
                {"time": "08:30", "event": "Initial Jobless Claims", "impact": "medium"},
                {"time": "10:00", "event": "ISM Services PMI", "impact": "high"},
            ],
        },
    }
