"""Hand-checked cases for the copy-lag simulation.   Run: python -m tests.test_copy_lag"""
import pandas as pd

from scripts.step5_copy_lag import PriceSeries, simulate_token

T = 1_000_000


def series(points):
    return PriceSeries(pd.DataFrame(points, columns=["ts", "price"]))


def trades(rows):
    return pd.DataFrame(rows, columns=["side", "size", "price", "ts"])


def close(a, b):
    assert a is not None and abs(a - b) < 1e-9, (a, b)


# 1) Buy at 40c, held to a $1 settlement. Price drifts up after their buy.
ps = series([(T, .40), (T + 300, .45), (T + 1800, .50), (T + 3600, .55), (T + 90000, 1.0)])
tr = trades([("BUY", 100, .40, T)])
close(simulate_token(tr, ps, 0, "actual"), 1 / .40 - 1)
close(simulate_token(tr, ps, 0), 1 / .40 - 1)
close(simulate_token(tr, ps, 5), 1 / .45 - 1)
close(simulate_token(tr, ps, 30), 1 / .50 - 1)
close(simulate_token(tr, ps, 5, friction=.01), 1 / .46 - 1)

# 2) Buy at 50c, sell everything at 60c an hour later (a "trader" round trip); market loses.
ps = series([(T, .50), (T + 300, .52), (T + 3600, .60), (T + 3900, .58), (T + 90000, 0.0)])
tr = trades([("BUY", 100, .50, T), ("SELL", 100, .60, T + 3600)])
close(simulate_token(tr, ps, 0, "actual"), .60 / .50 - 1)
close(simulate_token(tr, ps, 5), .58 / .52 - 1)                 # both legs 5 min late
close(simulate_token(tr, ps, 5, friction=.01), .57 / .53 - 1)

# 3) Half sold at 70c, half held to a $0 settlement.
ps = series([(T, .50), (T + 3600, .70), (T + 90000, 0.0)])
tr = trades([("BUY", 100, .50, T), ("SELL", 50, .70, T + 3600)])
close(simulate_token(tr, ps, 0, "actual"), (.5 * .70) / .50 - 1)

# 4) Market settles 10 minutes after their buy: a 30-minute copy is missed (0%).
ps = series([(T, .90), (T + 600, 1.0)])
tr = trades([("BUY", 100, .90, T)])
close(simulate_token(tr, ps, 30), 0.0)

# 5) Still-open market, position still held: not computable.
ps = series([(T, .40), (T + 300, .45)])
assert simulate_token(trades([("BUY", 100, .40, T)]), ps, 5) is None

print("COPY-LAG TESTS PASSED")
