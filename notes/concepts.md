# Concepts

- **Price = implied probability.** A share at 30¢ pays $1 if it wins, so the market thinks there's a ~30% chance.
- **Edge z-score.** Expected wins for a no-skill trader = sum of entry prices. z = (actual wins − expected) ÷ sqrt(Σ p(1−p)). A z of 3 or more is very unlikely to be luck. Current caveat: a "win" means the position made money, which includes positions sold early.
- **Why REDEEMABLE_LOST matters.** Losing shares are worth $0, so people rarely redeem them, and they never show up as CLOSED. Leave them out and everyone looks like a genius.
- **Proxy wallet.** Each Polymarket account trades through a proxy wallet address. That's the ID the API uses.
- **Leaderboard volume** is counted in shares, not USDC.
- **Copyability.** For a manual copier with $500, an edge only counts if it survives a delay of several minutes and fits small position sizes.
- **API field caveats (learned the hard way):** `total_cost_usdc` is unreliable on CLOSED positions, so use `avg_price × total_size`. Status labels don't separate wins from losses, so use PnL. Default sorts are biggest-PnL-first, so always pick the sort explicitly when sampling.
- **Survivorship in samples:** any cap or limit applied to a list sorted by profit produces fake geniuses. Sample by time, not by outcome.
- **Derived exit price** (Justin's idea): exit = avg_price + realized_pnl ÷ total_size. Exit at $1 or $0 means the bet was held to resolution, a "pick". Exit in between means it was sold early, i.e. in-play trading. Checked: 99.4% of derived exits fall in [0, 1].
- **Pickers vs traders.** Pickers choose a side and wait for the result, so alerts you approve by hand can copy them. Traders profit from buying and selling during events, which manual copying can't keep up with. `edge_z_held` scores only held-to-resolution bets. `flag_trader` = more than 50% of profit comes from early sales.
- **Equal stake vs their stake.** A copier with $500 puts roughly the same amount on every bet, while the wallet bets big when confident. Some wallets profit only because of that sizing (ilovecircle: +8.3% on his sizes, −3.1% with equal stakes). Always judge copyability with equal-stake returns.
- **Conviction filter.** Copy only the bets that are large *for that wallet* (top 25% of their own sizes). This recovers the sizing edge without needing their bankroll.
- **Price sensitivity.** A 2¢ worse entry wipes out a 2–5% edge. Wallets that buy cheap long shots or have 10%+ edges are much more robust to slippage and lag.
