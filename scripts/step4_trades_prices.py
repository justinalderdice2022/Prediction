"""Step 4: for a shortlist of candidate wallets, download their individual trades
(last ~55 days) and the 5-minute price history of every token they traded.
This is the raw material for the copy-lag backtest in step 5.

Run from the project root:   python -m scripts.step4_trades_prices
Options:
    --wallets ndb1 S-Works ...   backtest these usernames (or 0x addresses) instead
    --list                       just print the shortlist and stop

Shortlist (default): from data/outputs/wallet_stats.csv (run step 3 first), the top
SHORTLIST_PICKERS pickers by edge_z_held and top SHORTLIST_TRADERS traders by edge_z,
among wallets that pass every filter. Safe to re-run: finished wallets/tokens are cached.
"""
import argparse
import logging
import time

import pandas as pd

from src import api, config, db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")


def shortlist(con, names=None) -> pd.DataFrame:
    if names:
        w = pd.read_sql("SELECT wallet, user_name FROM wallets", con)
        sel = w[w["user_name"].isin(names) | w["wallet"].isin([n.lower() for n in names])].copy()
        sel["style"] = "manual"
        return sel
    s = pd.read_csv(config.OUTPUT_DIR / "wallet_stats.csv")
    s = s[s["copy_candidate"]]
    pickers = s[s["style"] == "picker"].sort_values("edge_z_held", ascending=False).head(config.SHORTLIST_PICKERS)
    traders = s[s["style"] == "trader"].sort_values("edge_z", ascending=False).head(config.SHORTLIST_TRADERS)
    return pd.concat([pickers, traders])[["wallet", "user_name", "style"]]


def fetch_trades(con, wallet: str, start: int) -> int:
    params = {"user": wallet, "start": start, "limit": 1000, "taker_only": "false"}
    n = 0
    for t in api.paginate("/v2/trades", params, resend_all=True, max_rows=config.MAX_TRADES_PER_WALLET):
        if t.get("proxy_wallet", wallet).lower() != wallet:
            continue   # with taker_only=false, keep only this wallet's own side of each fill
        con.execute(
            """INSERT OR IGNORE INTO trades (wallet, tx_hash, token_id, condition_id, side, size, price, ts, title, outcome)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (wallet, t.get("transaction_hash"), str(t.get("token_id")), t.get("condition_id"), t.get("side"),
             t.get("size"), t.get("price"), t.get("timestamp"), t.get("title"), t.get("outcome")))
        n += 1
    con.execute("INSERT OR REPLACE INTO trades_fetched VALUES (?,?,?)", (wallet, start, int(time.time())))
    con.commit()
    return n


def fetch_prices(con, token: str, start: int, now: int) -> int:
    """5-minute price history from `start`, in 15-day chunks (API limit), stopping once
    the market has settled (final point at exactly $0 or $1) or we reach now."""
    rows = []
    chunk = config.PRICE_CHUNK_DAYS * 86400 - 60
    a = start
    for _ in range(config.MAX_PRICE_CHUNKS):
        b = min(a + chunk, now)
        params = {"token_id": token, "start": a, "end": b,
                  "bucket_seconds": config.PRICE_BUCKET_SECONDS, "limit": 10000}
        pts = list(api.paginate("/v2/prices-history", params, resend_all=True))
        rows += [(token, p["timestamp"], p["price"], p.get("resolution_seconds", 0)) for p in pts]
        settled = any(p.get("resolution_seconds", 1) == 0 and p["price"] in (0, 1) for p in pts[-1:])
        if settled or b >= now:
            break
        a = b
    con.executemany("INSERT OR REPLACE INTO prices VALUES (?,?,?,?)", rows)
    con.execute("INSERT OR REPLACE INTO prices_fetched VALUES (?,?,?,?)", (token, start, now, len(rows)))
    con.commit()
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wallets", nargs="*", help="usernames or addresses to backtest")
    ap.add_argument("--list", action="store_true", help="print the shortlist and stop")
    args = ap.parse_args()

    con = db.connect()
    sl = shortlist(con, args.wallets)
    print(sl.to_string(index=False))
    if args.list or sl.empty:
        return

    now = int(time.time())
    start = now - config.TRADE_LOOKBACK_DAYS * 86400
    done = {w for (w,) in con.execute("SELECT wallet FROM trades_fetched WHERE start <= ?", (start + 86400,))}
    for i, (w, name) in enumerate(zip(sl["wallet"], sl["user_name"]), 1):
        if w in done:
            logging.info("[%d/%d] %s: trades already fetched", i, len(sl), name)
            continue
        logging.info("[%d/%d] %s: fetching trades...", i, len(sl), name)
        try:
            logging.info("    %d trades", fetch_trades(con, w, start))
        except Exception as e:
            logging.error("    failed: %s", e)

    # Price history for the most recent MAX_TOKENS_PER_WALLET markets each wallet bought
    # (skipping the last 2 days, which mostly haven't settled yet)
    q = f"""SELECT wallet, token_id, MIN(ts) AS first_ts FROM trades
            WHERE side='BUY' AND ts >= ? AND ts <= ? AND wallet IN ({','.join('?' * len(sl))})
            GROUP BY wallet, token_id"""
    wt = pd.read_sql(q, con, params=[start, now - 2 * 86400, *sl["wallet"]])
    wt = wt.sort_values("first_ts", ascending=False).groupby("wallet").head(config.MAX_TOKENS_PER_WALLET)
    tokens = wt.groupby("token_id")["first_ts"].min()
    have = dict(con.execute("SELECT token_id, n FROM prices_fetched WHERE n > 0").fetchall())
    todo = [(t, ts) for t, ts in tokens.items() if t not in have]
    logging.info("%d markets selected (max %d per wallet); %d need price history",
                 len(tokens), config.MAX_TOKENS_PER_WALLET, len(todo))
    fails = 0
    for i, (tok, first_ts) in enumerate(todo, 1):
        try:
            n = fetch_prices(con, tok, int(first_ts) - 3600, now)
            if i % 25 == 0 or n == 0:
                logging.info("[%d/%d] token %s...: %d price points", i, len(todo), tok[:12], n)
        except Exception as e:
            fails += 1
            logging.error("[%d/%d] token %s... failed: %s", i, len(todo), tok[:12], str(e)[:200])
            if fails >= 10 and fails == i:
                logging.error("first 10 requests all failed; stopping so we can fix it")
                return
    logging.info("done. Next: python -m scripts.step5_copy_lag")


if __name__ == "__main__":
    main()
