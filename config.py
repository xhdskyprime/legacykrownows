# config.py
# Central configuration file for the Kronos trading system (Top 3 Elite Setup).
# Focus: XAU/USD (Gold), GBP/USD, EUR/USD
# Max Positions per Pair: 10 Positions (Layering Searah Tren)
# High-Impact News Filter & Dynamic Trailing Stop

import os as _os
import platform as _platform

# ── Top 3 Elite Pairs ──
ACTIVE_PAIRS = [
    {"name": "XAUUSDm", "label": "XAU/USD (Gold)", "digits": 3, "lot": 0.01, "spread": 0.50},
    {"name": "GBPUSDm", "label": "GBP/USD",        "digits": 5, "lot": 0.03, "spread": 0.00020},
    {"name": "EURUSDm", "label": "EUR/USD",        "digits": 5, "lot": 0.03, "spread": 0.00015},
]

LOT_SIZE = {p["name"]: p["lot"] for p in ACTIVE_PAIRS}
SPREAD_USD = {p["name"]: p["spread"] for p in ACTIVE_PAIRS}
PAIR_DIGITS = {p["name"]: p["digits"] for p in ACTIVE_PAIRS}

# ── Max Layering per Pair ──
MAX_POSITIONS_PER_PAIR = 10

# ── News Filter ──
NEWS_FILTER_HOURS = [12, 13, 14, 18, 19]

# ── Spread Multiplier ──
SPREAD_MULTIPLIER = 1.5

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
