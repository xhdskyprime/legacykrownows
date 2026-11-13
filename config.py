# config.py
# Central configuration file for Kronos AI Auto-Trader.
# Optimized Elite Portfolio: Top 12 Profitable Instruments (Rank 1 - 12)
# Underperforming instruments (Rank 13 - 21) have been removed per user instruction.
# News Filter is DISABLED per user request for 24/7 momentum capture.

import os as _os
import platform as _platform

# ── Top 12 Elite Instruments (Rank 1 - 12 Leaderboard) ──
ACTIVE_PAIRS = [
    # ── Commodities & Precious Metals (Top Tier Performers) ──
    {"name": "XAUUSDm", "label": "Gold (XAU/USD)",      "digits": 3, "lot": 0.01, "spread": 0.35},
    {"name": "XAGUSDm", "label": "Silver (XAG/USD)",    "digits": 3, "lot": 0.01, "spread": 0.03},
    {"name": "USOILm",  "label": "Crude Oil (WTI)",     "digits": 3, "lot": 0.01, "spread": 0.02},

    # ── High-Momentum Equity Index ──
    {"name": "US30m",   "label": "Dow Jones 30",        "digits": 1, "lot": 0.05, "spread": 2.00},

    # ── High-Volatility Forex Crosses ──
    {"name": "GBPJPYm", "label": "GBP/JPY (Guppy)",     "digits": 3, "lot": 0.03, "spread": 0.025},
    {"name": "GBPAUDm", "label": "GBP/AUD",             "digits": 5, "lot": 0.03, "spread": 0.00025},
    {"name": "EURAUDm", "label": "EUR/AUD",             "digits": 5, "lot": 0.03, "spread": 0.00020},
    {"name": "AUDJPYm", "label": "AUD/JPY",             "digits": 3, "lot": 0.03, "spread": 0.015},

    # ── Forex Majors ──
    {"name": "EURUSDm", "label": "EUR/USD",             "digits": 5, "lot": 0.03, "spread": 0.00015},
    {"name": "GBPUSDm", "label": "GBP/USD",             "digits": 5, "lot": 0.03, "spread": 0.00020},
    {"name": "AUDUSDm", "label": "AUD/USD",             "digits": 5, "lot": 0.03, "spread": 0.00015},

    # ── Crypto (Elite) ──
    {"name": "ETHUSDm", "label": "Ethereum (ETH)",      "digits": 2, "lot": 0.10, "spread": 1.20},
]

LOT_SIZE = {p["name"]: p["lot"] for p in ACTIVE_PAIRS}
SPREAD_USD = {p["name"]: p["spread"] for p in ACTIVE_PAIRS}
PAIR_DIGITS = {p["name"]: p["digits"] for p in ACTIVE_PAIRS}

# ── Max Layering per Pair (Golden Setup: Sweet Spot Max 2 Layers) ──
MAX_POSITIONS_PER_PAIR = 2

# ── News Filter ──
ENABLE_NEWS_FILTER = False
NEWS_FILTER_HOURS = [12, 13, 14, 18, 19]

# ── Spread Multiplier ──
SPREAD_MULTIPLIER = 1.3

# ── MT5 File Bridge Paths ──
if _platform.system() == "Windows":
    _appdata = _os.environ.get("APPDATA", _os.path.expanduser("~\\AppData\\Roaming"))
    MT5_COMMON_FILES = _os.path.join(_appdata, "MetaQuotes", "Terminal", "Common", "Files")
else:
    MT5_COMMON_FILES = _os.path.expanduser(
        "~/Library/Application Support/net.metaquotes.wine.metatrader5"
        "/drive_c/users/user/AppData/Roaming/MetaQuotes/Terminal/Common/Files"
    )

SIGNAL_FILE = _os.path.join(MT5_COMMON_FILES, "signal.json")
SIGNAL_ACK_FILE = _os.path.join(MT5_COMMON_FILES, "signal_ack.json")
