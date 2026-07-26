"""
gex.py  --  The heart of the tool. Computes Gamma Exposure (GEX) from a raw
option chain, the way SpotGamma / Unusual Whales do under the hood.

This is intentionally written to be READABLE, not maximally fast. Read it
top to bottom and you'll understand exactly what every number on the
dashboard is "based on" -- nothing here is a black box.

THE IDEA (short version):
  Dealers (market makers) sell options to retail and hedge their risk by
  trading the underlying. Their hedging FLOW is predictable from how much
  gamma they hold. GEX measures the dollars of underlying dealers must trade
  per 1% move.
    - Positive GEX  -> dealers buy dips / sell rips -> price gets pinned, mean-reverts
    - Negative GEX  -> dealers sell dips / buy rips -> moves get amplified, trends
  The "gamma flip" is the price where net GEX crosses zero -- the regime line.
"""
import math


# --- standard normal probability density function -------------------------
def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def bs_gamma(spot: float, strike: float, t_years: float, iv: float, r: float) -> float:
    """
    Black-Scholes gamma for one option (calls and puts share the same gamma).

    gamma = N'(d1) / (S * sigma * sqrt(T))
    where d1 = [ln(S/K) + (r + sigma^2/2) * T] / (sigma * sqrt(T))

    Returns 0 for degenerate inputs (expired, zero IV) so the pipeline never
    blows up on a bad row in the chain.
    """
    if spot <= 0 or strike <= 0 or t_years <= 0 or iv <= 0:
        return 0.0
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t_years) / (iv * math.sqrt(t_years))
    return _norm_pdf(d1) / (spot * iv * math.sqrt(t_years))


def dollar_gamma(gamma: float, open_interest: float, spot: float) -> float:
    """
    Convert raw gamma into dollar GEX for a 1% move.

      $GEX = gamma * OI * 100 * S^2 * 0.01

    100 = contract multiplier (1 option = 100 shares).
    S^2 * 0.01 turns "gamma per $1" into "dollars of delta per 1% move".
    """
    return gamma * open_interest * 100.0 * spot * spot * 0.01


def compute_gex(chain: dict, spot: float, r: float) -> dict:
    """
    Aggregate a full chain into the GEX picture.

    `chain` is a dict:
        {
          "calls": [ {strike, oi, iv, t_years, oi_change}, ... ],
          "puts":  [ {strike, oi, iv, t_years, oi_change}, ... ],
        }

    SIGN CONVENTION (the one modeling choice that matters):
      We assume dealers are LONG calls and SHORT puts -- the common retail
      convention. So calls add POSITIVE dealer gamma, puts add NEGATIVE.
      This is an assumption, not a law. SpotGamma et al. tweak it. If your
      levels feel off, this is the first knob to revisit. <-- learn this.
    """
    by_strike = {}  # strike -> net dollar gamma

    def _add(rows, sign):
        for o in rows:
            g = bs_gamma(spot, o["strike"], o["t_years"], o["iv"], r)
            dg = sign * dollar_gamma(g, o["oi"], spot)
            by_strike[o["strike"]] = by_strike.get(o["strike"], 0.0) + dg

    _add(chain["calls"], +1.0)
    _add(chain["puts"], -1.0)

    strikes = sorted(by_strike.keys())
    profile = [{"strike": k, "gex": by_strike[k]} for k in strikes]
    net_gex = sum(by_strike.values())

    # --- gamma flip: where cumulative GEX (low->high strike) crosses zero ---
    # NOTE: this is the quick approximation. The "true" zero-gamma level
    # recomputes gamma at each candidate spot. Good enough for a morning bias;
    # marked as a future upgrade in the README.
    flip = _zero_cross(profile)

    # --- walls: biggest positive (call) and most negative (put) gamma -------
    call_wall = max(profile, key=lambda p: p["gex"]) if profile else None
    put_wall = min(profile, key=lambda p: p["gex"]) if profile else None

    # --- put/call positioning ----------------------------------------------
    call_oi = sum(o["oi"] for o in chain["calls"])
    put_oi = sum(o["oi"] for o in chain["puts"])
    pc_ratio = (put_oi / call_oi) if call_oi else 0.0
    call_oi_chg = sum(o.get("oi_change", 0) for o in chain["calls"])
    put_oi_chg = sum(o.get("oi_change", 0) for o in chain["puts"])

    # --- control node / magnet: strike holding the most |dealer gamma| ------
    # This is the price the market tends to gravitate toward (the "pin").
    control = max(profile, key=lambda p: abs(p["gex"])) if profile else None
    control_node = control["strike"] if control else None

    # --- ATM implied vol (nearest strike to spot) for expected-move math ----
    atm_iv = _atm_iv(chain, spot)

    regime = "positive" if spot >= (flip or spot) else "negative"

    return {
        "spot": spot,
        "net_gex": net_gex,
        "regime": regime,
        "gamma_flip": flip,
        "control_node": control_node,
        "atm_iv": round(atm_iv, 4),
        "call_wall": call_wall["strike"] if call_wall else None,
        "put_wall": put_wall["strike"] if put_wall else None,
        "profile": profile,
        "put_call_ratio": pc_ratio,
        "call_oi": call_oi,
        "put_oi": put_oi,
        "call_oi_change": call_oi_chg,
        "put_oi_change": put_oi_chg,
    }


def _atm_iv(chain: dict, spot: float) -> float:
    """Average implied vol of the call and put nearest to spot."""
    def nearest(rows):
        best, bd = 0.0, None
        for o in rows:
            d = abs(o["strike"] - spot)
            if bd is None or d < bd:
                bd, best = d, o["iv"]
        return best
    c, p = nearest(chain["calls"]), nearest(chain["puts"])
    vals = [v for v in (c, p) if v]
    return sum(vals) / len(vals) if vals else 0.0


def _zero_cross(profile: list) -> float | None:
    """Find the strike level where cumulative GEX flips sign."""
    if not profile:
        return None
    cum = 0.0
    prev_strike, prev_cum = None, 0.0
    for p in profile:
        cum += p["gex"]
        if prev_strike is not None and (prev_cum < 0 <= cum or prev_cum > 0 >= cum):
            # linear interpolation between the two bracketing strikes
            span = cum - prev_cum
            if span != 0:
                frac = -prev_cum / span
                return round(prev_strike + frac * (p["strike"] - prev_strike), 2)
        prev_strike, prev_cum = p["strike"], cum
    return profile[len(profile) // 2]["strike"]  # fallback: middle strike
