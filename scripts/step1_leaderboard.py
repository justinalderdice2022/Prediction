"""Step 1: pull the top wallets from Polymarket's all-time PnL leaderboard.

Run from the project root:   python -m scripts.step1_leaderboard
"""
import logging
import time

from src import api, config, db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def main():
    con = db.connect()
    params = {"time_period": "all", "sort_by": "PNL", "category": "overall", "limit": 1000}
    now = int(time.time())
    n = 0
    for row in api.paginate("/v2/leaderboard", params, max_rows=config.LEADERBOARD_SIZE):
        con.execute(
            """INSERT INTO wallets (wallet, user_name, rank_pnl, lb_pnl, lb_volume, verified, fetched_at)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(wallet) DO UPDATE SET user_name=excluded.user_name, rank_pnl=excluded.rank_pnl,
                 lb_pnl=excluded.lb_pnl, lb_volume=excluded.lb_volume, verified=excluded.verified,
                 fetched_at=excluded.fetched_at""",
            (row["user_id"].lower(), row.get("user_name"), row.get("rank"), row.get("pnl"),
             row.get("volume"), int(bool(row.get("verified"))), now),
        )
        n += 1
    con.commit()
    logging.info("saved %d leaderboard wallets to %s", n, config.DB_PATH)
    top = con.execute("SELECT rank_pnl, user_name, wallet, ROUND(lb_pnl) FROM wallets ORDER BY rank_pnl LIMIT 10").fetchall()
    for r in top:
        print(r)


if __name__ == "__main__":
    main()
