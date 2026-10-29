"""Offline smoke test: runs steps 1-3 against fake API responses (no internet).

Run from the project root:   python -m tests.test_offline
"""
import random
import tempfile
import time
from pathlib import Path

from src import api, config

tmp = Path(tempfile.mkdtemp())
config.DATA_DIR = tmp
config.DB_PATH = tmp / "test.db"
config.OUTPUT_DIR = tmp / "outputs"
config.LEADERBOARD_SIZE = 30
config.MAX_POSITIONS_PER_STATUS = 25   # small so the cap + hyperactive flag get exercised

random.seed(1)
NOW = int(time.time())
WALLETS = [f"0x{i:040x}" for i in range(30)]


def fake_positions(wallet, status):
    i = int(wallet, 16)
    rng = random.Random(i)                     # same draws for every status call
    rows = []
    n_mkts = 200 if i == 1 else (5 if i % 5 == 0 else 40)  # wallet 1 = hyperactive; every 5th = too few markets
    skill = 0.15 if i % 3 == 0 else 0.0       # every 3rd wallet has real edge
    for k in range(n_mkts):
        p = 0.97 if i % 7 == 0 else rng.uniform(0.1, 0.9)   # every 7th is a penny picker
        won = rng.random() < min(p + skill, 0.99)
        true_status = "CLOSED" if k % 2 == 0 else ("REDEEMABLE" if won else "REDEEMABLE_LOST")
        if true_status != status:
            continue
        cost = 100.0
        pnl = cost * (1 / p - 1) if won else -cost
        rows.append({"token_id": f"{wallet}-{status}-{k}", "condition_id": f"c{k}-{i}", "status": status,
                     "title": f"Market {k}", "avg_price": p, "total_size": cost / p, "total_cost_usdc": cost, "total_pnl": pnl,
                     "realized_pnl": pnl, "unrealized_pnl": 0, "first_entry_at": NOW - 86400 * 30,
                     "last_event_at": NOW - 86400 * 2, "negative_risk": False})
    return rows


def fake_get(path, params=None, **kw):
    params = params or {}
    if path == "/v2/leaderboard":
        page = int(params.get("cursor", 0))
        chunk = WALLETS[page * 20:(page + 1) * 20]
        nxt = str(page + 1) if (page + 1) * 20 < len(WALLETS) else None
        return {"data": [{"user_id": w, "rank": WALLETS.index(w) + 1, "pnl": 1000.0, "volume": 5.0,
                          "user_name": f"user{WALLETS.index(w)}", "verified": False} for w in chunk],
                "pagination": {"next_cursor": nxt}}
    if path == "/v2/positions":
        assert "user" in params, "cursor pages must resend the user anchor"
        rows = fake_positions(params["user"], params.get("status", "CLOSED"))
        # wallet 2 simulates an API that keeps handing back the same cursor
        nxt = "stuck" if params["user"] == WALLETS[2] else None
        return {"data": rows, "pagination": {"next_cursor": nxt}}
    raise AssertionError(path)


api.get = fake_get

from scripts import step1_leaderboard, step2_positions, step3_wallet_stats  # noqa: E402
import sys  # noqa: E402

step1_leaderboard.main()
sys.argv = ["step2"]
step2_positions.main()
step3_wallet_stats.main()
print("\nOFFLINE TEST PASSED")
