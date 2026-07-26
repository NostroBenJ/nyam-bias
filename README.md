# NYAM Bias Engine

A local dashboard that builds a **probabilistic pre-market bias** from options
positioning — GEX, gamma flip, call/put walls, SMT divergence, session levels —
for whatever ticker you point it at. Defaults to SPY. Writes a journal note to
Obsidian each morning, and has Claude built in so you can interrogate the setup.

> It is **not** a predictor. It produces a weighted lean, the reasoning behind
> it, and explicit if/then scenarios. You make the call.

---

## Quick start

```bash
pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:8000**. Boots in mock mode — synthetic but realistic
data, zero keys, zero cost — so you can see the whole thing before wiring
anything live. Or just double-click `start_dashboard.bat`, which sets the env
vars for you and opens the browser.

**Change ticker** in the top-left: type a symbol or pick from the list. The
whole board repoints — GEX, levels, bias, and the track record, which is kept
per ticker.

---

## Data

Set in `start_dashboard.bat`, or as env vars.

| Mode | Env | What you get |
|---|---|---|
| Mock | `NYAM_MOCK=1` | Offline synthetic data. No keys, no cost. |
| Yahoo | `NYAM_MOCK=0 NYAM_PROVIDER=yahoo` | Free, ~15-min delayed chains. Fine for a pre-market bias built off prior-session OI. |
| Unusual Whales | `NYAM_MOCK=0 NYAM_PROVIDER=uw UW_API_KEY=...` | Real-time chains, **day-over-day OI**, flow alerts, dark pool prints. |

**Before trusting the UW path, probe it** — endpoint coverage varies by tier:

```bash
python -m data.unusual_whales probe SPY
```

It hits every endpoint the adapter uses and prints which ones your key reaches.
Anything that fails degrades to Yahoo per-piece rather than breaking the load,
and the snapshot records why in `sources` / `uw_errors`.

The UW paths were written against the published OpenAPI spec but have **not yet
been run against a live key** — the probe is how you find out what's real.

### Why UW is worth it here specifically

`oi_change` is the one input the free path cannot supply. yfinance gives a
single snapshot with no previous session to diff against, so the **OI Shift**
signal in `bias_engine.py` has been reading a hardcoded `0` the entire time it
has run on live data. UW carries `prev_oi`, which makes that signal real.

---

## Ask Claude

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

Bottom-right button, or **Ctrl/Cmd+K**. The chat sees the current snapshot for
the selected ticker — spot, net GEX, walls, flip, every signal and its reason,
the track record — so "why is this short?" gets an answer about the numbers on
screen, not a textbook explanation of gamma.

The key stays server-side; the browser only ever talks to `/api/chat`. The
snapshot is re-injected fresh each turn and stripped from older turns, so the
model never reasons off a stale spot price. Model is `CLAUDE_MODEL` in
`config.py` (`claude-opus-5`; `claude-sonnet-5` is cheaper and still strong).

Without a key the dashboard works fine — chat is disabled and the morning brief
falls back to a template.

---

## How it's wired

```
data/data_sources.py   <- the ONLY file that touches the outside world
  |- mock_data.py            synthetic
  |- yfinance                free, delayed
  \- unusual_whales.py       paid, real-time + flow + dark pool
        |
        v
analysis/gex.py        Black-Scholes gamma -> $GEX per strike -> net GEX,
                       zero-gamma flip, call/put walls, control node
analysis/levels.py     prior session H/L/M, overnight range, confluences
analysis/smt.py        cross-market divergence (SPY vs QQQ)
analysis/derived.py    expected move, multi-expiry confluence, level map
analysis/bias_engine.py  weighted combine -> LEAN + score + per-signal reasons
analysis/tracker.py    records each call, grades it after the close
        |
        v
claude_brief.py   structured signals -> readable brief (Claude or template)
chat.py           the in-app chat, grounded in the live snapshot
pipeline.py       runs the chain into one snapshot dict
app.py            FastAPI: dashboard, /api/*, pre-market scheduler
```

Everything downstream of `data_sources.py` reads the same shape, so swapping
providers never touches the math or the UI.

---

## Verifying the math

```bash
python verify_gex.py
```

13 numerical checks. Gamma is finite-differenced against an independent
Black-Scholes pricer rather than compared to a hardcoded number; the gamma flip
is verified to be an actual zero of net gamma with a sign change across it; the
regime label is checked against the sign of net GEX; walls are checked to sit on
the correct side of spot.

This is not ceremony. Every one of those checks corresponds to a bug that was
live in this code:

- **regime was inverted.** It was derived from `spot >= gamma_flip` rather than
  the sign of net gamma, so a QQQ book at **-$3.68B** — deeply short gamma —
  was labelled "positive gamma / expect mean-reversion." That is the top-line
  read on the whole dashboard, and it was backwards.
- **the flip was float noise.** The old cumulative-across-strikes method fired
  on a sign change among worthless deep-OTM strikes and returned **421 against
  a 684 spot**. When no crossing existed it returned the middle strike as a
  fabricated answer. It now re-prices the chain at candidate spots and bisects
  the crossing nearest to spot, and returns `None` when there isn't one.
- **walls had no side constraint**, so the "Put Wall / Floor — BUY DIPS" marker
  could render *above* the current price.
- **the overnight low was 5% off**, set by a zero-volume Yahoo phantom bar
  (`O 684.85 / C 684.76 / L 649.28`), over a window that was a full regular
  session rather than an overnight.

Independently: Unusual Whales' own spec defines call wall, put wall, and gamma
flip exactly the way `analysis/gex.py` now does. The **Level Check** panel
compares the two live and reports drift — it does not overwrite ours with
theirs, because two computations that agree are evidence and one silently
replacing the other is not.

---

## Track record — does the bias actually work?

Every weekday the app saves its call and grades it over **the window you
actually trade: open → 12:00 ET** (`GRADE_EXIT_TIME`). **Directional accuracy
is the number that matters, and the baseline is 50%.**

This used to grade open→close, which scored the call over ~4 hours you aren't
in the market. It is not a cosmetic difference: over 60 SPY sessions the two
windows disagree on **45% of days**, including outright sign flips (2026-05-12
was −0.60% at noon and +0.53% by the close). A lean that was right when you
closed out was being marked a loss you never took.

- **Per ticker.** Records are keyed `TICKER|date` — pooling a SPY hit rate with
  an NVDA one describes no instrument you actually trade.
- **Per-ticker band.** A move smaller than the band counts as flat, which is
  how NEUTRAL scores. One global band doesn't work: 0.175% leaves ~27% of SPY
  sessions flat but ~40% of QQQ's, because QQQ simply moves more. Measured
  values live in `GRADE_BAND_BY_TICKER`.
- **The band is measured, not guessed** — 0.175% is what leaves the same share
  of SPY days flat over the morning window as 0.15% did over the full day, so
  NEUTRAL stays exactly as hard to score. Re-derive it on fresh data:

  ```bash
  python measure_grade_band.py SPY QQQ
  ```

  It also reports stability, and currently flags both tickers as **unstable** —
  the ratio swings 0.65→0.92 across halves of a 60-session sample. Re-run
  periodically; don't chase small moves in the number.
- **Every outcome is stamped with the rule that graded it** (`open->12:00@0.175`).
  Change the window or the band later and the panel will tell you the history
  is mixed rather than blending two measurements into one meaningless rate.
- Persisted to `data_store/records.json` (mock mode uses a separate file).
- **Small samples are noise.** The panel says so until ~30+ graded days. This
  is the feature that tells you whether any of this has an edge — let it.

---

## Tuning

- `config.py` — ticker list, expirations rolled into GEX, schedule, grading band.
- `analysis/bias_engine.py` — the `WEIGHTS` dict. Starting guesses, not gospel.
- `analysis/gex.py` — the dealer **sign convention** (long calls / short puts).
  If your levels feel systematically off, that is the first knob to revisit.

---

## Known limitations

- **Econ calendar is stubbed.** News comes from a lightweight Yahoo pull; the
  `high_impact` flag is only ever set in mock mode. Wire a real calendar feed
  if you want the conviction cut to fire on live data.
- **SMT needs a real overnight session.** On weekends and before the first
  post-close print there is no Globex range, so it reports `no_data` rather
  than comparing the prior-day range against itself and calling it "in sync."
- **Expected move floors at one day.** Fine for a morning bias; overstates
  intraday 0DTE.
- **The UW adapter is unverified against a live key.** Paths come from the
  published spec. Run the probe.

_Probabilistic lean from positioning data. Not a prediction. Not financial advice._
