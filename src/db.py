"""SQLite storage. One file (data/polymarket.db) you can open with any SQLite viewer."""
import sqlite3
from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS wallets (
    wallet        TEXT PRIMARY KEY,
    user_name     TEXT,
    rank_pnl      INTEGER,
    lb_pnl        REAL,      -- all-time realized PnL from leaderboard (USDC)
    lb_volume     REAL,      -- leaderboard volume (shares, not USDC)
    verified      INTEGER,
    fetched_at    INTEGER,
    positions_done INTEGER DEFAULT 0   -- 1 once positions are downloaded
);

CREATE TABLE IF NOT EXISTS positions (
    wallet          TEXT,
    token_id        TEXT,
    condition_id    TEXT,
    status          TEXT,
    title           TEXT,
    slug            TEXT,
    event_id        TEXT,
    event_slug      TEXT,
    outcome         TEXT,
    end_date        TEXT,
    avg_price       REAL,
    total_size      REAL,
    current_size    REAL,
    current_price   REAL,
    total_cost_usdc REAL,
    entry_fees_usdc REAL,
    realized_pnl    REAL,
    unrealized_pnl  REAL,
    total_pnl       REAL,
    first_entry_at  INTEGER,
    last_event_at   INTEGER,
    negative_risk   INTEGER,
    PRIMARY KEY (wallet, token_id)
);
CREATE INDEX IF NOT EXISTS idx_pos_wallet ON positions(wallet);
CREATE INDEX IF NOT EXISTS idx_pos_cond ON positions(condition_id);

-- Individual fills (step 4), for the copy-lag backtest
CREATE TABLE IF NOT EXISTS trades (
    wallet        TEXT,
    tx_hash       TEXT,
    token_id      TEXT,
    condition_id  TEXT,
    side          TEXT,      -- BUY / SELL from the wallet's point of view
    size          REAL,      -- shares
    price         REAL,
    ts            INTEGER,
    title         TEXT,
    outcome       TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trades_uniq ON trades(wallet, tx_hash, token_id, side, size, price, ts);
CREATE TABLE IF NOT EXISTS trades_fetched (wallet TEXT PRIMARY KEY, start INTEGER, fetched_at INTEGER);

-- Price history per outcome token (step 4), 5-minute buckets + settlement point
CREATE TABLE IF NOT EXISTS prices (
    token_id TEXT,
    ts       INTEGER,
    price    REAL,
    res      INTEGER,      -- 0 = exact tick / settlement, else bucket width (s)
    PRIMARY KEY (token_id, ts)
);
CREATE TABLE IF NOT EXISTS prices_fetched (token_id TEXT PRIMARY KEY, start INTEGER, end_ts INTEGER, n INTEGER);
"""


def connect():
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(config.DB_PATH, timeout=60)  # wait if another step is writing
    con.executescript(SCHEMA)
    # Columns added after the first release: add them to existing databases too.
    cols = {r[1] for r in con.execute("PRAGMA table_info(wallets)")}
    if "hyperactive" not in cols:
        con.execute("ALTER TABLE wallets ADD COLUMN hyperactive INTEGER DEFAULT 0")
    return con
