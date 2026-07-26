# NYAM Bias Engine

A local desktop app that builds a **probabilistic pre-market bias** for your
Nasdaq (MNQ) trading off options positioning — GEX, gamma flip, call/put walls,
SMT divergence, session levels — and writes a journal note to Obsidian each
morning. Runs on **free data**. Optional Claude-written brief.

> It is **not** a predictor. It produces a weighted lean + the reasoning + "if/then"
> scenarios. You make the call.

---

## Quick start (zero keys, zero cost)

```bash
pip install -r requirements.txt   # only fastapi/uvicorn/apscheduler needed for mock mode
python app.py
```

Open **http://127.0.0.1:8000**. It boots in **mock mode** with realistic
synthetic data so you can see the whole thing before wiring anything live.

---

## Going live (still free)

The only file that touches the outside world is `data/data_sources.py`.
It pulls free, ~15-min-delayed option chains from Yahoo Finance — which is
fine, because a pre-market bias is built off prior-session open interest that
doesn't move minute-to-minute before the open.

```bash
pip install yfinance
export NYAM_MOCK=0
python app.py
```

### Optional: Claude-written brief
Without a key, you get a clean templated brief (free). To use Claude:
```bash
pip install anthropic
export ANTHROPIC_API_KEY=sk-ant-...
```
Cost is fractions of a cent (Haiku) to a couple cents (Sonnet) per morning.
Model is set in `config.py` (`CLAUDE_MODEL`).

### Optional: point it at your Obsidian vault
```bash
export NYAM_VAULT="/path/to/your/Obsidian Vault"
```
Notes land in `<vault>/NYAM Bias/YYYY-MM-DD.md`. Auto-written at 09:25 ET
on weekdays, or hit **Log to Obsidian** in the UI anytime.

---

## How it's wired

```
data_sources.py   ← swap providers here ONLY (mock ↔ yfinance ↔ anything)
      │
      ▼
analysis/gex.py        Black-Scholes gamma → $GEX per strike → net GEX,
                       gamma flip, call/put walls, put/call positioning
analysis/levels.py     prior session H/L/M, overnight range, confluences
analysis/smt.py        QQQ vs SPY overnight divergence (NQ/ES proxy)
analysis/bias_engine.py  weighted combine → LEAN + score + per-signal reasons
      │
      ▼
claude_brief.py    structured signals → readable brief (Claude or template)
pipeline.py        runs the whole chain into one snapshot dict
app.py             FastAPI: serves dashboard, /api/bias, pre-market scheduler
logging_obsidian.py  writes the daily markdown note
```

Everything downstream reads the same data shape, so changing data providers
never touches the math or the UI.

## Tune it to how you trade
- `config.py` → tickers, expirations rolled into GEX, refresh/log times.
- `analysis/bias_engine.py` → the `WEIGHTS` dict. These are starting guesses,
  not gospel. Adjust them to match what actually works for you.
- `analysis/gex.py` → the dealer **sign convention** (long calls / short puts).
  If your levels feel off, that's the first knob to revisit.

## Track record (does the bias actually work?)
Every morning the app saves its prediction; after each close it grades the call
against that session's open→close move and keeps a running hit-rate. The panel
shows **directional accuracy** (the number that matters — baseline is 50%),
overall accuracy, a dot strip of recent results, and a per-bias-type breakdown.

- Predictions persist to `data_store/records.json` (live) — plain JSON you can open.
- Grading: LONG correct if close > open beyond the band, SHORT if below, NEUTRAL
  if it stayed inside the band. Band is `GRADE_BAND_PCT` in `config.py`.
- Mock mode ships ~22 days of synthetic history so the panel isn't empty; live
  mode starts blank and builds its own record.
- **Small samples are noise.** The panel says so until you have ~30+ graded days.
  This is the feature that tells you whether any of this has an edge — let it.

## Honest limitations / roadmap
- **Gamma flip** uses a cumulative-cross approximation, not the full
  recompute-at-spot zero-gamma method. Fine for a morning bias; upgrade later.
- **OI change** needs day-over-day data. yfinance gives a single snapshot, so
  live `oi_change` is 0 until you persist a daily snapshot (save each morning's
  chain to a small SQLite/CSV and diff — good next project).
- **Econ calendar** is stubbed. Free option: scrape/ingest a calendar feed, or
  keep checking Forex Factory manually and flag high-impact days in `config`.
- **Flow alerts / dark pool** (Unusual Whales' real edge) aren't here — free
  data can't replicate them. The GEX/positioning core is what matters for bias.

_Probabilistic lean from positioning data. Not a prediction. Not financial advice._
