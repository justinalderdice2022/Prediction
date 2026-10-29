"""Project-wide settings. Change values here rather than inside scripts."""
from pathlib import Path
import time

# --- Paths -------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
DB_PATH = DATA_DIR / "polymarket.db"
OUTPUT_DIR = DATA_DIR / "outputs"

# --- API ---------------------------------------------------------------------
DATA_API = "https://data-api.polymarket.com"
GAMMA_API = "https://gamma-api.polymarket.com"
REQUEST_TIMEOUT = 30          # seconds per request
MIN_SECONDS_BETWEEN_CALLS = 0.25  # polite pacing; raise if you see 429s

# --- Research scope ----------------------------------------------------------
LOOKBACK_MONTHS = 18
WINDOW_START = int(time.time()) - LOOKBACK_MONTHS * 30 * 24 * 3600

# How many wallets to pull from the all-time PnL leaderboard.
# ~1.7M+ wallets have traded, so the top 0.1% is roughly 1,700-2,000 wallets.
LEADERBOARD_SIZE = 2000

# Per-wallet, per-status cap. Wallets with this many settled positions in the
# window are almost certainly bots/high-frequency traders we couldn't copy by hand,
# so we stop downloading and mark them "hyperactive" instead of waiting hours.
MAX_POSITIONS_PER_STATUS = 5000

# --- Copy-lag backtest (step4 / step5) -----------------------------------------
# Polymarket keeps 5-minute price history for ~60 days (1-minute only ~7 days),
# so the lag replay is limited to recent trades.
TRADE_LOOKBACK_DAYS = 55
PRICE_BUCKET_SECONDS = 300
COPY_LAGS_MINUTES = [0, 5, 30, 60]
SHORTLIST_PICKERS = 15        # top pickers (by edge_z_held) to backtest
SHORTLIST_TRADERS = 5         # top traders (by edge_z) to backtest
MAX_TOKENS_PER_WALLET = 250   # backtest at most this many recent markets per wallet
MAX_TRADES_PER_WALLET = 20000 # stop downloading a wallet's fills after this many (newest first)
PRICE_CHUNK_DAYS = 15         # API limit: one prices-history request may span at most 15 days
MAX_PRICE_CHUNKS = 4          # follow a market for at most 60 days after the first buy

# --- Filters used in wallet_stats.py (first guesses; tune after looking at data)
INACTIVE_DAYS = 30            # no settled/closed position in this many days = gone quiet
MIN_MARKETS = 20              # need at least this many resolved markets to judge skill
NEAR_CERTAIN_PRICE = 0.95     # entries above this are "picking up pennies"
MAX_NEAR_CERTAIN_SHARE = 0.5  # flag wallets where most entries are near-certain
