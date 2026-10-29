# Ideas / backlog

- Also pull the monthly and weekly leaderboards. The all-time board is full of inactive legends (e.g. Theo4), so recent boards would surface traders who are winning now.
- Market categories from the Gamma API (event slug → tags), so we can compare edge by category.
- "Copy lag" backtest: if we had entered 5 / 30 / 60 minutes after the trader, at the price then, would we still profit? Needs `/v2/trades` plus `/v2/prices-history`. **This is the key test before going live.**
- Out-of-sample check: pick traders using months 1–12 and test them on months 13–18. Do the winners stay winners?
- Cluster wallets that look like one person (same markets, same timing).
- Consensus signal: alert when several top wallets enter the same side within a short window.
- Alert delivery: Telegram bot or email, polling `/v2/trades?user=` for watched wallets.
- Alerts with a conviction filter: only alert when a watched wallet's bet is ≥ its own 75th-percentile size.
- Per-wallet copy rule from the backtest: which lag is acceptable and which bet sizes to copy, stored in a small config file the alert bot reads.
- Polymarket US matching: map each international signal (market title, outcome) to the same market on Polymarket US, and log both prices at alert time. This measures the venue price gap live.
