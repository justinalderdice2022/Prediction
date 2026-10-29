"""Step 3: turn raw positions into one row of stats per wallet, flag the wallets
that are not worth copying, and rank the rest.

Run from the project root:   python -m scripts.step3_wallet_stats
Output: data/outputs/wallet_stats.csv  (open in VS Code, LibreOffice, or pandas)

Key idea, the "edge z-score":
    If you buy at 30c, the market is saying you win ~30% of the time.
    Summing entry prices over all of a wallet's bets gives the number of wins a
    no-skill trader would expect. Comparing actual wins to that, scaled by the
    natural randomness (sum of p*(1-p)), gives a z-score. z around 0 = no better
    than the market; z of 3+ = very unlikely to be luck. This is a first-pass
    heuristic: "win" here means the position made money, which also counts
    positions sold early at a profit.
"""
import time

import numpy as np
import pandas as pd

from src import config, db


def wallet_stats(pos: pd.DataFrame) -> pd.DataFrame:
    pos = pos[pos["last_event_at"].fillna(0) >= config.WINDOW_START].copy()
    # The API's total_cost_usdc is 0 or far too small on most CLOSED rows (see notes/bugs.md),
    # so rebuild cost from avg entry price x shares bought. Status labels are also unreliable
    # (losses come back as REDEEMABLE), so wins/losses are judged by PnL, never by status.
    pos["total_cost_usdc"] = (pos["avg_price"] * pos["total_size"]).fillna(0)
    pos = pos[pos["total_cost_usdc"] > 0]
    pos["won"] = pos["total_pnl"] > 0
    pos["p"] = pos["avg_price"].clip(0.001, 0.999)
    pos["hold_hours"] = (pos["last_event_at"] - pos["first_entry_at"]) / 3600
    # Average exit price, derived: realized_pnl = (exit - entry) x shares. For still-held
    # shares use the settled price. Exit at $1 or $0 = held to resolution (a "pick");
    # anything in between = sold early (in-play trading, which alerts can't keep up with).
    exited = pos["current_size"].fillna(0) < 0.01 * pos["total_size"]
    pos["exit_price"] = np.where(exited, pos["avg_price"] + pos["realized_pnl"].fillna(0) / pos["total_size"],
                                 pos["current_price"])
    pos["held"] = (pos["exit_price"] > 0.995) | (pos["exit_price"] < 0.005)

    # Per wallet+market: did the wallet hold more than one outcome in the same market?
    per_mkt = pos.groupby(["wallet", "condition_id"]).agg(
        mkt_pnl=("total_pnl", "sum"), n_outcomes=("token_id", "nunique")).reset_index()

    rows = []
    for w, g in pos.groupby("wallet"):
        m = per_mkt[per_mkt["wallet"] == w]
        cost = g["total_cost_usdc"].sum()
        pnl = g["total_pnl"].sum()
        expected = g["p"].sum()
        var = (g["p"] * (1 - g["p"])).sum()
        pos_pnl = m["mkt_pnl"].clip(lower=0).sum()
        h = g[g["held"]]
        h_var = (h["p"] * (1 - h["p"])).sum()
        rows.append({
            "wallet": w,
            "n_positions": len(g),
            "n_markets": g["condition_id"].nunique(),
            "pnl": pnl,
            "cost": cost,
            "roi": pnl / cost if cost else np.nan,
            "market_win_rate": (m["mkt_pnl"] > 0).mean(),
            "avg_entry_price": np.average(g["p"], weights=g["total_cost_usdc"]),
            "edge_z": (g["won"].sum() - expected) / np.sqrt(var) if var > 0 else np.nan,
            "near_certain_share": g.loc[g["p"] >= config.NEAR_CERTAIN_PRICE, "total_cost_usdc"].sum() / cost,
            "both_sides_share": (m["n_outcomes"] > 1).mean(),
            "top_market_pnl_share": m["mkt_pnl"].max() / pos_pnl if pos_pnl > 0 else np.nan,
            "median_hold_hours": g["hold_hours"].median(),
            "median_bet_usdc": g["total_cost_usdc"].median(),
            "days_since_last_activity": (time.time() - g["last_event_at"].max()) / 86400,
            # --- picker vs trader --------------------------------------------------
            "pct_held": len(h) / len(g),
            "edge_z_held": ((h["exit_price"] > 0.5).sum() - h["p"].sum()) / np.sqrt(h_var) if h_var > 0 else np.nan,
            "roi_held": h["total_pnl"].sum() / h["total_cost_usdc"].sum() if len(h) else np.nan,
            "early_sale_pnl_share": (g.loc[~g["held"], "total_pnl"].sum() / pnl) if pnl > 0 else np.nan,
        })
    s = pd.DataFrame(rows)
    if s.empty:
        return s

    # --- Flags: reasons a wallet is probably not worth copying ---------------------
    s["flag_few_markets"] = s["n_markets"] < config.MIN_MARKETS
    s["flag_penny_picker"] = s["near_certain_share"] > config.MAX_NEAR_CERTAIN_SHARE
    s["flag_market_maker"] = s["both_sides_share"] > 0.3
    s["flag_one_hit"] = s["top_market_pnl_share"] > 0.5
    s["flag_too_fast"] = s["median_hold_hours"] < 1     # hard to copy by hand
    s["flag_losing_in_window"] = s["pnl"] <= 0
    s["flag_inactive"] = s["days_since_last_activity"] > config.INACTIVE_DAYS   # nothing to copy
    # Style label (NOT a filter): "trader" = over half the profit comes from selling before
    # resolution; "picker" = profit comes from holding winners. The copy-lag backtest decides
    # which traders are copyable, so they are not excluded here.
    s["style"] = np.where(s["early_sale_pnl_share"] > 0.5, "trader", "picker")
    flag_cols = [c for c in s.columns if c.startswith("flag_")]
    s["n_flags"] = s[flag_cols].sum(axis=1)
    s["copy_candidate"] = s["n_flags"] == 0
    return s.sort_values(["copy_candidate", "edge_z_held"], ascending=[False, False])


def main():
    con = db.connect()
    pos = pd.read_sql("SELECT * FROM positions", con)
    wallets = pd.read_sql("SELECT wallet, user_name, rank_pnl, lb_pnl, hyperactive FROM wallets", con)
    if pos.empty:
        print("No positions yet. Run step1 and step2 first.")
        return
    stats = wallet_stats(pos)
    if stats.empty:
        print("No positions with a usable cost inside the window.")
        return
    s = wallets.merge(stats, on="wallet", how="inner")
    # Hyperactive = hit the download cap in step 2 (bot / high-frequency; not hand-copyable)
    s["flag_hyperactive"] = s.pop("hyperactive").fillna(0).astype(bool)
    flag_cols = [c for c in s.columns if c.startswith("flag_")]
    s["n_flags"] = s[flag_cols].sum(axis=1)
    s["copy_candidate"] = s["n_flags"] == 0
    s = s.sort_values(["copy_candidate", "edge_z_held"], ascending=[False, False])
    config.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = config.OUTPUT_DIR / "wallet_stats.csv"
    s.to_csv(out, index=False)

    flag_cols = [c for c in s.columns if c.startswith("flag_")]
    print(f"\n{len(s)} wallets analysed, {int(s['copy_candidate'].sum())} pass every filter\n")
    print("Why wallets were filtered out:")
    print(s[flag_cols].sum().sort_values(ascending=False).to_string(), "\n")
    show = ["rank_pnl", "user_name", "style", "days_since_last_activity", "n_markets", "pct_held", "edge_z_held", "roi_held", "edge_z",
            "avg_entry_price", "median_bet_usdc"]
    c = s[s["copy_candidate"]]
    print("Top PICKERS, ranked by edge on bets held to resolution:")
    print(c[c["style"] == "picker"][show].head(20).round(2).to_string(index=False))
    print("\nTRADERS (profit mostly from selling early), ranked by overall edge:")
    print(c[c["style"] == "trader"].sort_values("edge_z", ascending=False)[show].head(10).round(2).to_string(index=False))
    print(f"\nFull table: {out}")


if __name__ == "__main__":
    main()
