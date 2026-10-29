"""Diagnostic: why do some shortlisted wallets have no copy-lag results?
For each wallet: trades downloaded, tokens bought, tokens with price history,
tokens whose market has settled, and tokens that made it into step 5's results.

Run: python -m scripts.diag_step45
"""
import time

import pandas as pd

from src import config, db
from scripts.step4_trades_prices import shortlist


def main():
    con = db.connect()
    sl = shortlist(con)
    start = int(time.time()) - config.TRADE_LOOKBACK_DAYS * 86400
    pf = pd.read_sql("SELECT token_id, n FROM prices_fetched", con)
    last = pd.read_sql("""SELECT p.token_id, p.price FROM prices p
                          JOIN (SELECT token_id, MAX(ts) m FROM prices GROUP BY token_id) x
                          ON p.token_id = x.token_id AND p.ts = x.m""", con)
    settled = set(last.loc[(last["price"] >= 0.999) | (last["price"] <= 0.001), "token_id"])
    with_px = set(pf.loc[pf["n"] > 0, "token_id"])
    no_px = set(pf.loc[pf["n"] == 0, "token_id"])
    try:
        res = pd.read_csv(config.OUTPUT_DIR / "copy_lag_by_token.csv", dtype={"token_id": str})
    except FileNotFoundError:
        res = pd.DataFrame(columns=["wallet", "token_id"])
    fetched = dict(con.execute("SELECT wallet, fetched_at FROM trades_fetched").fetchall())

    rows = []
    for w, name in zip(sl["wallet"], sl["user_name"]):
        t = pd.read_sql("SELECT * FROM trades WHERE wallet=? AND ts>=?", con, params=(w, start))
        bt = set(t.loc[t["side"] == "BUY", "token_id"])
        last_trade = pd.read_sql("SELECT MAX(ts) m FROM trades WHERE wallet=?", con, params=(w,))["m"].iloc[0]
        rows.append({
            "user": str(name)[:22],
            "trades_fetched": w in fetched,
            "n_trades": len(t),
            "n_buys": int((t["side"] == "BUY").sum()),
            "n_sells": int((t["side"] == "SELL").sum()),
            "days_since_last_trade": round((time.time() - last_trade) / 86400, 1) if last_trade else None,
            "tokens_bought": len(bt),
            "with_prices": len(bt & with_px),
            "empty_prices": len(bt & no_px),
            "settled": len(bt & settled),
            "in_results": int((res["wallet"] == w).sum()),
        })
    pd.set_option("display.width", 250)
    print(pd.DataFrame(rows).to_string(index=False))
    print("\nTotal tokens with price history fetched:", len(pf), "| empty series:", len(no_px),
          "| settled:", len(settled))


if __name__ == "__main__":
    main()
