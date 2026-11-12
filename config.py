# config.py
# Central configuration file for Kronos AI Multi-Asset Auto-Trader.
# High-Volatility Setup: 23 Pairs across Crypto, Commodities, Indices, and Forex.
# News Filter is DISABLED per user request.

import os as _os
import platform as _platform

# ── 23 High-Volatility Multi-Asset Instruments ──
ACTIVE_PAIRS = [
    # ── Crypto (24/7 High Volatility) ──
    {"name": "BTCUSDm", "label": "Bitcoin (BTC)",       "digits": 2, "lot": 0.01, "spread": 6.50},
    {"name": "ETHUSDm", "label": "Ethereum (ETH)",      "digits": 2, "lot": 0.10, "spread": 1.20},
    {"name": "SOLUSDm", "label": "Solana (SOL)",        "digits": 4, "lot": 0.05, "spread": 0.60},
    {"name": "DOGEUSDm","label": "Dogecoin (DOGE)",     "digits": 6, "lot": 0.01, "spread": 0.0006},

    # ── Commodities & Metals ──
    {"name": "XAUUSDm", "label": "Gold (XAU/USD)",      "digits": 3, "lot": 0.01, "spread": 0.35},
    {"name": "XAGUSDm", "label": "Silver (XAG/USD)",    "digits": 3, "lot": 0.01, "spread": 0.03},
    {"name": "USOILm",  "label": "Crude Oil (WTI)",     "digits": 3, "lot": 0.01, "spread": 0.02},

    # ── Indices (High Momentum) ──
    {"name": "US30m",   "label": "Dow Jones 30",        "digits": 1, "lot": 0.05, "spread": 2.00},
    {"name": "USTECm",  "label": "Nasdaq 100",          "digits": 2, "lot": 0.05, "spread": 1.50},

    # ── High-Volatility Forex Crosses (Wide Pips) ──
    {"name": "GBPJPYm", "label": "GBP/JPY (Guppy)",     "digits": 3, "lot": 0.03, "spread": 0.025},
    {"name": "EURJPYm", "label": "EUR/JPY",             "digits": 3, "lot": 0.03, "spread": 0.020},
    {"name": "CADJPYm", "label": "CAD/JPY",             "digits": 3, "lot": 0.03, "spread": 0.015},
    {"name": "AUDJPYm", "label": "AUD/JPY",             "digits": 3, "lot": 0.03, "spread": 0.015},
    {"name": "NZDJPYm", "label": "NZD/JPY",             "digits": 3, "lot": 0.03, "spread": 0.018},
    {"name": "GBPAUDm", "label": "GBP/AUD",             "digits": 5, "lot": 0.03, "spread": 0.00025},
    {"name": "EURAUDm", "label": "EUR/AUD",             "digits": 5, "lot": 0.03, "spread": 0.00020},

    # ── Forex Majors ──
    {"name": "GBPUSDm", "label": "GBP/USD",             "digits": 5, "lot": 0.03, "spread": 0.00020},
    {"name": "EURUSDm", "label": "EUR/USD",             "digits": 5, "lot": 0.03, "spread": 0.00015},
    {"name": "USDJPYm", "label": "USD/JPY",             "digits": 3, "lot": 0.03, "spread": 0.015},
    {"name": "AUDUSDm", "label": "AUD/USD",             "digits": 5, "lot": 0.03, "spread": 0.00015},
    {"name": "USDCADm", "label": "USD/CAD",             "digits": 5, "lot": 0.03, "spread": 0.00018},
    {"name": "NZDUSDm", "label": "NZD/USD",             "digits": 5, "lot": 0.03, "spread": 0.00018},
    {"name": "USDCHFm", "label": "USD/CHF",             "digits": 5, "lot": 0.03, "spread": 0.00018},
]

LOT_SIZE = {p["name"]: p["lot"] for p in ACTIVE_PAIRS}
SPREAD_USD = {p["name"]: p["spread"] for p in ACTIVE_PAIRS}
PAIR_DIGITS = {p["name"]: p["digits"] for p in ACTIVE_PAIRS}

# ── Max Layering per Pair ──
MAX_POSITIONS_PER_PAIR = 5

# ── News Filter ──
# Mati/Disabled per permintaan user agar trading bebas 24/7 tanpa terjeda berita
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
