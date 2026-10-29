# Bugs & fixes

Format: date — symptom — cause — fix

- 2026-10-29 — Offline test flagged almost every wallet as a market maker — the fake data generator reused market IDs across status calls — made the generator deterministic per wallet (a test-only bug; real code unaffected)
- 2026-10-29 — step2 sat silently on wallet #2 (swisstony) for minutes — likely a high-volume trader with huge numbers of positions; the script only printed once a wallet finished, so we couldn't tell slow from stuck — added progress lines per wallet/status/5 pages, a guard against repeated cursors, and a cap (`MAX_POSITIONS_PER_STATUS=5000` in config). Wallets hitting the cap get `hyperactive=1` and `flag_hyperactive` in step3 (bots/HFT aren't hand-copyable anyway).
- 2026-10-29 — Sync: three files (config.py, db.py, api.py) reported "written" to the desktop but stayed old → `no attribute MAX_POSITIONS_PER_STATUS` / `no such column: hyperactive` — file-sync glitch, not code — re-sent and now byte-compare every file after each sync.
- 2026-10-29 — Absurd ROIs (3,331%) in first real step3 run — API's `total_cost_usdc` is 0 on ~78% of CLOSED rows (and too small on the rest), and step3 dropped zero-cost rows, discarding most wins — cost now = `avg_price × total_size`; zero-cost filter uses that. ROIs now −46%…+250%.
- 2026-10-29 — No rows ever labelled REDEEMABLE_LOST; losers come back as REDEEMABLE with current_price 0 — API status labels unreliable — never use status for win/loss; use PnL (and current_price 1/0 for settled).
- 2026-10-29 — Capped ("hyperactive") wallets showed ~100% win rate — CLOSED default sort is biggest-realized-PnL first, so the 5,000-row cap kept only top wins — step2 now sorts by TIMESTAMP DESC (unbiased recent sample); `--redo-hyperactive` re-downloads them.
- 2026-10-29 — step4 price history failed for most tokens: `'start' to 'end' must span at most 15 days` — undocumented API limit on /v2/prices-history — fetch in 15-day chunks, stop at settlement (`PRICE_CHUNK_DAYS`, `MAX_PRICE_CHUNKS`); fake API in the test now enforces the limit.
- 2026-10-29 — step4 wanted price history for 33,357 markets after the shortlist picked up very active wallets — cap at the 250 most recent markets per wallet (`MAX_TOKENS_PER_WALLET`) and 20k fills per wallet (`MAX_TRADES_PER_WALLET`).
- 2026-10-29 — 12 of 20 shortlisted wallets had zero trades in 55 days — not a bug: they stopped trading (ilovecircle 161 days, hot2trot 101 days) — step3 `flag_inactive` (no activity in `INACTIVE_DAYS`=30).
- 2026-10-29 — S-Works' lag-30 mean of +95% came from one LoL game (bought at ~3c mid-game, won: +2,757%) — means are fragile at small n — step5 adds median, win rate, and a capped mean.
