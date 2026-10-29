"""Offline end-to-end test of step 4 (download) + step 5 (backtest) with a fake API.
Run: python -m tests.test_step45_offline"""
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

from src import api, config, db

tmp = Path(tempfile.mkdtemp())
config.DATA_DIR, config.DB_PATH, config.OUTPUT_DIR = tmp, tmp / "t.db", tmp / "out"
NOW = int(time.time())
W = "0x" + "a" * 40
calls = {"trades": 0, "prices": 0}

con = db.connect()
con.execute("INSERT INTO wallets (wallet, user_name, rank_pnl) VALUES (?,?,?)", (W, "fakepicker", 1))
con.commit()
config.OUTPUT_DIR.mkdir(parents=True)
pd.DataFrame([{"wallet": W, "user_name": "fakepicker", "style": "picker", "copy_candidate": True,
               "edge_z_held": 3.0, "edge_z": 3.0}]).to_csv(config.OUTPUT_DIR / "wallet_stats.csv", index=False)


def fake_get(path, params=None, **kw):
    params = params or {}
    if path == "/v2/trades":
        calls["trades"] += 1
        rows = []
        for k in range(10):   # 10 markets: buys at 40c, 6 settle at $1, 4 at $0
            t = NOW - 86400 * (20 - k)
            rows.append({"proxy_wallet": W, "transaction_hash": f"0x{k}", "token_id": f"tok{k}",
                         "condition_id": f"c{k}", "side": "BUY", "size": 100, "price": 0.40,
                         "timestamp": t, "title": f"Game {k}", "outcome": "Yes"})
        page = int(params.get("cursor", 0))       # two pages of 5 to exercise paging
        return {"data": rows[page * 5:(page + 1) * 5], "pagination": {"next_cursor": "1" if page == 0 else None}}
    if path == "/v2/prices-history":
        calls["prices"] += 1
        if params["end"] - params["start"] > 15 * 86400:      # the real API's limit
            raise RuntimeError("400: 'start' to 'end' must span at most 15 days")
        k = int(params["token_id"][3:])
        t0 = NOW - 86400 * (20 - k)
        pts = [{"timestamp": t0 - 300, "price": .40, "resolution_seconds": 300},
               {"timestamp": t0 + 300, "price": .44, "resolution_seconds": 300},
               {"timestamp": t0 + 1800, "price": .48, "resolution_seconds": 300},
               {"timestamp": t0 + 86400, "price": 1.0 if k < 6 else 0.0, "resolution_seconds": 0}]
        return {"data": pts, "pagination": {"next_cursor": None}}
    raise AssertionError(path)


api.get = fake_get
from scripts import step4_trades_prices, step5_copy_lag  # noqa: E402

sys.argv = ["step4"]
step4_trades_prices.main()
first = dict(calls)
step4_trades_prices.main()                     # second run must use the cache
assert calls == first, f"re-run should not call the API again: {first} -> {calls}"
step5_copy_lag.main()

r = pd.read_csv(config.OUTPUT_DIR / "copy_lag_by_wallet.csv").iloc[0]
assert r["n_bets"] == 10, r
expect_actual = (6 * (1 / .40 - 1) + 4 * -1) / 10        # = 0.5
assert abs(r["actual"] - expect_actual) < 1e-9, r["actual"]
assert abs(r["hist_0"] - expect_actual) < 1e-9, r["hist_0"]
assert abs(r["lag_5"] - (6 * (1 / .44 - 1) - 4) / 10) < 1e-9
assert r["lag_30"] < r["lag_5"] < r["actual"]
print("\nSTEP 4+5 OFFLINE TEST PASSED")
