# config.py
# Central configuration file for Kronos AI Auto-Trader.
# High-Efficiency Elite Portfolio (Cleaned: US30, Silver, and ETH removed per user request).
# Active: Gold, Crude Oil, and Top Stable Forex Crosses/Majors.
# Configured for Exness Cent Account (USC) with 'c' symbol suffix.
# Golden Setup: Sweet Spot Max 2 Positions per Pair.
# News Filter is DISABLED per user request for 24/7 momentum capture.

import os as _os
import platform as _platform

# ── Elite Stable Instruments (Exness Cent Account 'c' Suffix) ──
ACTIVE_PAIRS = [
    # ── Commodities & Energy (Top Tier Performers) ──
    {"name": "XAUUSDc", "label": "Gold (XAU/USD)",      "digits": 3, "lot": 0.01, "spread": 0.35},
    {"name": "USOILc",  "label": "Crude Oil (WTI)",     "digits": 3, "lot": 0.01, "spread": 0.02},

    # ── High-Volatility Forex Crosses ──
    {"name": "GBPJPYc", "label": "GBP/JPY (Guppy)",     "digits": 3, "lot": 0.03, "spread": 0.025},
    {"name": "GBPAUDc", "label": "GBP/AUD",             "digits": 5, "lot": 0.03, "spread": 0.00025},
    {"name": "EURAUDc", "label": "EUR/AUD",             "digits": 5, "lot": 0.03, "spread": 0.00020},
    {"name": "AUDJPYc", "label": "AUD/JPY",             "digits": 3, "lot": 0.03, "spread": 0.015},

    # ── Forex Majors (High Liquidity, Smooth Trends) ──
    {"name": "EURUSDc", "label": "EUR/USD",             "digits": 5, "lot": 0.03, "spread": 0.00015},
    {"name": "GBPUSDc", "label": "GBP/USD",             "digits": 5, "lot": 0.03, "spread": 0.00020},
    {"name": "AUDUSDc", "label": "AUD/USD",             "digits": 5, "lot": 0.03, "spread": 0.00015},
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
