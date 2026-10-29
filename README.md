# Prediction — Polymarket top-trader research

Goal: find the wallets in Polymarket's top ~0.1% that show **real, repeatable
skill** (not luck, bots, or market-making), learn what they bet on, and
eventually get **alerts** when they trade so we can copy by hand. Automation later.

Decisions so far: see `logs/` (one file per session) and `notes/`.

## Setup (once)

```bash
cd /home/usselmanlab/Justin/Prediction
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m tests.test_offline      # should end with "OFFLINE TEST PASSED"
```

## Pipeline

Always run from the project root, with the venv active.

| Step | Command | What it does | Time |
|---|---|---|---|
| 1 | `python -m scripts.step1_leaderboard` | Top 2,000 wallets by all-time PnL → `wallets` table | ~1 min |
| 2 | `python -m scripts.step2_positions --limit 50` | Settled positions for the first 50 wallets (test run) | few min |
| 2 | `python -m scripts.step2_positions` | All remaining wallets. Resumable: Ctrl-C and re-run anytime | ~1-3 h |
| 3 | `python -m scripts.step3_wallet_stats` | Per-wallet stats, filters, picker/trader label, ranking → `data/outputs/wallet_stats.csv` | seconds |
| 4 | `python -m scripts.step4_trades_prices` | Last ~55 days of trades for the shortlist + 5-min price history of every token they traded. Cached/resumable. `--list` shows the shortlist; `--wallets a b` picks your own | ~10-30 min |
| 5 | `python -m scripts.step5_copy_lag` | Copy-lag backtest (copy 0/5/30/60 min late, +1c costs, big-bets-only) + 18-month price sensitivity → `data/outputs/copy_lag_*.csv`, `price_sensitivity.csv` | seconds |

Tests (no internet): `python -m tests.test_offline`, `python -m tests.test_copy_lag`, `python -m tests.test_step45_offline`.

Data lives in `data/polymarket.db` (SQLite; VS Code's "SQLite Viewer" extension can open it).

## What step 3 measures

- **edge_z**: are they winning more often than their entry prices imply? ~0 = no edge, 3+ = very unlikely to be luck.
- **roi**: PnL ÷ money put in, over the lookback window (18 months).
- Flags that remove a wallet from the candidate list:
  - `few_markets` (< 20 markets — too little evidence)
  - `penny_picker` (mostly buys at 95c+ — tiny edge, not copyable at $500)
  - `market_maker` (often holds both sides of a market)
  - `one_hit` (> half their profit from one market)
  - `too_fast` (median hold < 1 hour — can't copy by hand)
  - `losing_in_window` (made their money before the window)

All thresholds live in `src/config.py`.

## Layout

```
src/        config.py (settings), api.py (HTTP client), db.py (SQLite schema)
scripts/    step1.., step2.., step3..  — the pipeline
tests/      test_offline.py — runs the whole pipeline on fake data
data/       database + outputs (not for git)
logs/       one markdown log per work session
notes/      ideas.md, concepts.md, bugs.md — running notes across sessions
```
