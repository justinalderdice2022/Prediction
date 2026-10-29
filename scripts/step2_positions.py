"""Step 2: for each leaderboard wallet, download its settled/closed positions
from the lookback window. Safe to stop and re-run: finished wallets are skipped.

Run from the project root:   python -m scripts.step2_positions
Optional:                     python -m scripts.step2_positions --limit 50   (quick test)

Why three statuses: a losing position held to resolution is usually never
redeemed, so it shows up as REDEEMABLE_LOST, not CLOSED. Leaving those out
would make every trader look like they almost never lose.
"""
import argparse
import logging

from src import api, config, db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")

STATUSES = ["CLOSED", "REDEEMABLE", "REDEEMABLE_LOST"]
COLS = ["wallet", "token_id", "condition_id", "status", "title", "slug", "event_id", "event_slug",
        "outcome", "end_date", "avg_price", "total_size", "current_size", "current_price",
        "total_cost_usdc", "entry_fees_usdc", "realized_pnl", "unrealized_pnl", "total_pnl",
        "first_entry_at", "last_event_at", "negative_risk"]


def fetch_wallet(con, wallet: str) -> int:
    n = 0
    hyper = False
    for status in STATUSES:
        # Newest first, so if the cap cuts a wallet off we keep an unbiased recent sample.
        # (The default sort for CLOSED is biggest-win-first, which made capped wallets look perfect.)
        params = {"user": wallet, "status": status, "limit": 1000, "start": config.WINDOW_START,
                  "sort_by": "TIMESTAMP", "sort_direction": "DESC"}
        n_status = 0
        for p in api.paginate("/v2/positions", params, max_rows=config.MAX_POSITIONS_PER_STATUS):
            n_status += 1
            row = {
                **{c: p.get(c) for c in COLS},
                "wallet": wallet,
                "status": p.get("status") or status,
                "negative_risk": int(bool(p.get("negative_risk"))),
            }
            con.execute(
                f"INSERT OR REPLACE INTO positions ({','.join(COLS)}) VALUES ({','.join('?' * len(COLS))})",
                [row[c] for c in COLS],
            )
            n += 1
        logging.info("    %s: %d", status, n_status)
        if n_status >= config.MAX_POSITIONS_PER_STATUS:
            hyper = True
    con.execute("UPDATE wallets SET positions_done=1, hyperactive=? WHERE wallet=?", (int(hyper), wallet))
    con.commit()
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="only process this many wallets")
    ap.add_argument("--redo-hyperactive", action="store_true",
                    help="delete and re-download wallets that hit the cap")
    args = ap.parse_args()

    con = db.connect()
    if args.redo_hyperactive:
        hw = [w for (w,) in con.execute("SELECT wallet FROM wallets WHERE hyperactive=1")]
        con.executemany("DELETE FROM positions WHERE wallet=?", [(w,) for w in hw])
        con.execute("UPDATE wallets SET positions_done=0, hyperactive=0 WHERE hyperactive=1")
        con.commit()
        logging.info("reset %d hyperactive wallets for re-download", len(hw))
    todo = [w for (w,) in con.execute(
        "SELECT wallet FROM wallets WHERE positions_done=0 ORDER BY rank_pnl").fetchall()]
    if args.limit:
        todo = todo[: args.limit]
    logging.info("%d wallets to fetch", len(todo))
    for i, w in enumerate(todo, 1):
        logging.info("[%d/%d] %s ...", i, len(todo), w)
        try:
            n = fetch_wallet(con, w)
            logging.info("[%d/%d] %s: %d positions", i, len(todo), w, n)
        except Exception as e:  # keep going; failed wallets stay positions_done=0 for a re-run
            logging.error("[%d/%d] %s failed: %s", i, len(todo), w, e)


if __name__ == "__main__":
    main()
