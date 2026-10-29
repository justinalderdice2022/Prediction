"""Step 5: the copy-lag backtest. "If I had copied this wallet N minutes late, at the
market price at that moment, would I still make money?"

Run from the project root:   python -m scripts.step5_copy_lag
Output: printed tables + data/outputs/copy_lag_by_wallet.csv, copy_lag_by_token.csv,
        price_sensitivity.csv

PART A — lag replay (last ~55 days, from step 4 data)
  For each wallet and each outcome token they traded:
    * we copy every BUY: entry price = market price LAG minutes after their buy
    * we copy every SELL the same way: exit = market price LAG minutes after their sell
    * whatever they didn't sell is held to settlement ($1 or $0)
  We put the same stake on every token they trade (what a $500 copier would do),
  so "mean return" = average % return per copied bet.
  Columns: actual = their own fill prices (no lag); hist_0 = same thing using the
  price-history series (checks the method: should be close to actual); lag_5/30/60;
  lag_5_cost = lag 5 plus 1c worse on every buy and sell (spread/slippage).
  If the market has already settled when our copy would arrive, the copy is "missed"
  and counts as 0% return. se = standard error of lag_5 (a rough +/- for the average).
  med_ / win_ / capped_ columns are outlier-resistant: median return, % of copies that
  made money, and the mean with each bet's gain capped at +100%. Trust these over the
  plain means when n_bets is small.
  PART A2 repeats this copying only each wallet's big bets (top 25% of their own sizes),
  because several wallets' edge lives in how much they bet, not in every bet.

PART B — price sensitivity (full 18 months, positions data, held-to-resolution bets)
  ROI if you had paid +1c, +2c, +5c more than they did on every bet.
"""
import numpy as np
import pandas as pd

from src import config, db

FRICTION = 0.01   # 1 cent per side for the "_cost" column


class PriceSeries:
    """Last observed price at or before t, for one token (5-minute buckets)."""

    def __init__(self, df: pd.DataFrame):
        df = df.sort_values("ts")
        self.ts = df["ts"].to_numpy()
        self.px = df["price"].to_numpy()
        last = self.px[-1] if len(self.px) else np.nan
        self.settle = 1.0 if last >= 0.999 else (0.0 if last <= 0.001 else None)
        self.settle_ts = self.ts[-1] if self.settle is not None else None

    def at(self, t: float):
        i = np.searchsorted(self.ts, t, side="right") - 1
        return None if i < 0 else float(self.px[i])

    def settled_by(self, t: float) -> bool:
        return self.settle is not None and t >= self.settle_ts


def simulate_token(tr: pd.DataFrame, ps: PriceSeries, lag_min: float, mode: str = "lag", friction: float = 0.0):
    """Return % return of copying one wallet on one token, or None if not computable.
    mode: 'actual' uses their fill prices; 'lag' uses the price series at t + lag."""
    buys, sells = tr[tr["side"] == "BUY"], tr[tr["side"] == "SELL"]
    bought = buys["size"].sum()
    if bought <= 0:
        return None
    sold = min(sells["size"].sum(), bought)
    f = sold / bought
    if f < 0.99 and ps.settle is None:
        return None                                   # still open: outcome unknown
    lag = lag_min * 60

    # Entry: size-weighted over their buys
    if mode == "actual":
        entry = (buys["size"] * buys["price"]).sum() / bought
    else:
        if all(ps.settled_by(t + lag) for t in buys["ts"]):
            return 0.0                                # market already over when we arrive: missed
        pts = [(s, ps.at(t + lag)) for t, s in zip(buys["ts"], buys["size"]) if not ps.settled_by(t + lag)]
        if any(p is None for _, p in pts):
            return None
        w = sum(s for s, _ in pts)
        entry = sum(s * p for s, p in pts) / w + friction
    if not (0 < entry < 1):
        return None

    # Exit: their sells (scaled to our position), the rest held to settlement
    exit_val = 0.0
    if sold > 0:
        # If they sold more than they bought in the window (older holdings), scale sells down
        scale = min(1.0, bought / sells["size"].sum())
        for t, s, p in zip(sells["ts"], sells["size"], sells["price"]):
            share = s * scale / bought          # fraction of our position sold here; sums to f
            if mode == "actual":
                px = p
            else:
                px = ps.at(t + lag)
                if px is None:
                    return None
                if not ps.settled_by(t + lag):
                    px -= friction
            exit_val += share * px
    if f < 1:
        if ps.settle is None:            # sold >=99% before an unsettled end: treat as fully sold
            exit_val /= f
        else:
            exit_val += (1 - f) * ps.settle
    return exit_val / entry - 1


def lag_replay(con) -> tuple[pd.DataFrame, pd.DataFrame]:
    trades = pd.read_sql("SELECT * FROM trades", con)
    if trades.empty:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    prices = pd.read_sql("SELECT token_id, ts, price FROM prices", con)
    names = pd.read_sql("SELECT wallet, user_name FROM wallets", con)
    series = {t: PriceSeries(g) for t, g in prices.groupby("token_id")}

    cols = {"actual": ("actual", 0, 0.0), "hist_0": ("lag", 0, 0.0)}
    for L in config.COPY_LAGS_MINUTES:
        if L > 0:
            cols[f"lag_{L}"] = ("lag", L, 0.0)
    cols["lag_5_cost"] = ("lag", 5, FRICTION)

    rows = []
    for (w, tok), g in trades.groupby(["wallet", "token_id"]):
        ps = series.get(tok)
        if ps is None or len(ps.ts) == 0:
            continue
        r = {"wallet": w, "token_id": tok, "title": g["title"].iloc[0], "outcome": g["outcome"].iloc[0],
             "first_buy": g.loc[g["side"] == "BUY", "ts"].min(),
             "their_stake": (g.loc[g["side"] == "BUY", "size"] * g.loc[g["side"] == "BUY", "price"]).sum()}
        for c, (mode, L, fr) in cols.items():
            r[c] = simulate_token(g, ps, L, mode, fr)
        rows.append(r)
    tok = pd.DataFrame(rows)
    tok = tok.dropna(subset=list(cols))                # same set of bets in every column
    tok = tok.merge(names, on="wallet", how="left")

    def summarize(g):
        out = {"n_bets": len(g)}
        for c in cols:
            out[c] = g[c].mean()
        out["se"] = g["lag_5"].std(ddof=1) / np.sqrt(len(g)) if len(g) > 1 else np.nan
        # Robust versions: one lucky in-play entry (e.g. buying at 3c mid-game) can dominate a mean
        out["med_lag_5"] = g["lag_5"].median()
        out["med_lag_30"] = g["lag_30"].median() if "lag_30" in g else np.nan
        out["win_lag_5"] = (g["lag_5"] > 0).mean()
        out["capped_lag_5"] = g["lag_5"].clip(upper=1.0).mean()   # each bet's gain capped at +100%
        out["missed_at_60"] = (g[f"lag_{max(config.COPY_LAGS_MINUTES)}"] == 0).mean()
        return pd.Series(out)

    by_w = tok.groupby(["user_name"]).apply(summarize, include_groups=False).reset_index()
    by_w = by_w.sort_values("lag_5", ascending=False)
    # "Conviction filter": only copy bets in the top 25% of that wallet's own bet sizes
    q75 = tok.groupby("wallet")["their_stake"].transform(lambda x: x.quantile(0.75))
    tok["big_bet"] = tok["their_stake"] >= q75
    big = tok[tok["big_bet"]]
    by_w_big = big.groupby(["user_name"]).apply(summarize, include_groups=False).reset_index() \
        if not big.empty else pd.DataFrame()
    if not by_w_big.empty:
        by_w_big = by_w_big.sort_values("lag_5", ascending=False)
    return by_w, tok, by_w_big


def price_sensitivity(con, wallets) -> pd.DataFrame:
    pos = pd.read_sql("SELECT p.*, w.user_name FROM positions p JOIN wallets w USING(wallet)", con)
    pos = pos[pos["wallet"].isin(wallets) & (pos["last_event_at"] >= config.WINDOW_START)].copy()
    pos = pos[(pos["avg_price"] * pos["total_size"]) > 0]
    exited = pos["current_size"].fillna(0) < 0.01 * pos["total_size"]
    pos["exit_price"] = np.where(exited, pos["avg_price"] + pos["realized_pnl"].fillna(0) / pos["total_size"],
                                 pos["current_price"])
    held = pos[(pos["exit_price"] > 0.995) | (pos["exit_price"] < 0.005)].copy()
    held["payout"] = (held["exit_price"] > 0.5).astype(float)
    rows = []
    for u, g in held.groupby("user_name"):
        r = {"user_name": u, "n_held": len(g)}
        for d in (0, 0.01, 0.02, 0.05):
            ok = g[g["avg_price"] + d < 1]
            cost = (ok["total_size"] * (ok["avg_price"] + d)).sum()
            r[f"roi_+{int(d * 100)}c"] = (ok["total_size"] * (ok["payout"] - ok["avg_price"] - d)).sum() / cost
            # equal-stake version (what a fixed-$ copier gets)
            r[f"eq_+{int(d * 100)}c"] = ((ok["payout"] / (ok["avg_price"] + d)) - 1).mean()
        rows.append(r)
    out = pd.DataFrame(rows)
    return out.sort_values("eq_+2c", ascending=False) if not out.empty else out


def pct_table(df: pd.DataFrame) -> str:
    show = df.copy()
    for c in show.columns:
        if c not in ("user_name", "n_bets"):
            show[c] = (df[c] * 100).round(1).astype(str) + "%"
    show["n_bets"] = df["n_bets"].astype(int)
    return show.to_string(index=False)


def main():
    con = db.connect()
    pd.set_option("display.width", 250)
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    by_w, tok, by_w_big = lag_replay(con)
    if by_w.empty:
        print("No trades yet. Run step 4 first.")
    else:
        by_w.to_csv(config.OUTPUT_DIR / "copy_lag_by_wallet.csv", index=False)
        tok.to_csv(config.OUTPUT_DIR / "copy_lag_by_token.csv", index=False)
        print("\nPART A: average return per copied bet (equal stake), last ~55 days")
        print("  actual = their prices | hist_0 = method check | lag_N = copied N min late | "
              "lag_5_cost = +1c worse each side")
        print(pct_table(by_w))
        if not by_w_big.empty:
            by_w_big.to_csv(config.OUTPUT_DIR / "copy_lag_big_bets.csv", index=False)
            print("\nPART A2: same, copying ONLY their big bets (top 25% of each wallet's bet sizes)")
            print(pct_table(by_w_big))
        all_row = tok[[c for c in tok.columns if c == "actual" or c.startswith(("hist", "lag"))]].mean() * 100
        print("\nAll wallets pooled (%):", all_row.round(2).to_dict(), f" n_bets={len(tok)}")

    wallets = tok["wallet"].unique() if not tok.empty else \
        pd.read_sql("SELECT DISTINCT wallet FROM trades", con)["wallet"].unique()
    if len(wallets):
        ps = price_sensitivity(con, wallets)
        if ps.empty:
            print("\nPART B: no positions data for these wallets (run step 2).")
            return
        ps.to_csv(config.OUTPUT_DIR / "price_sensitivity.csv", index=False)
        print("\nPART B: return on held-to-resolution bets if you paid more than they did (18 months)")
        print("  roi_ = their bet sizes | eq_ = same stake on every bet (copier's view)")
        print((ps.set_index(["user_name", "n_held"]) * 100).round(1).to_string())
    print(f"\nFiles in {config.OUTPUT_DIR}")


if __name__ == "__main__":
    main()
