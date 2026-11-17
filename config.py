# config.py
# Central configuration file for Kronos AI Auto-Trader.
# Kronos Hybrid AI-Grid v3.0 (Stepped Trailing + Adaptive Pullback Grid)
# 28 High-Volume Instruments on Exness Cent Account (USC) with 'c' symbol suffix.
# Multi-Asset Portfolio: Commodities, High-Volatility Crosses, Majors & Crypto.

import os as _os
import platform as _platform

# ── 28 Active Instruments (Exness Cent Account 'c' Suffix) ──
ACTIVE_PAIRS = [
    # ── Commodities & Energy ──
    {"name": "XAUUSDc", "label": "Gold (XAU/USD)",      "digits": 3, "lot": 0.01, "spread": 0.35},
    {"name": "USOILc",  "label": "Crude Oil (WTI)",     "digits": 3, "lot": 0.01, "spread": 0.020},
    {"name": "UKOILc",  "label": "Brent Oil (UKOIL)",   "digits": 3, "lot": 0.01, "spread": 0.020},

    # ── High-Volatility JPY Crosses (Active Swings) ──
    {"name": "GBPJPYc", "label": "GBP/JPY (Guppy)",     "digits": 3, "lot": 0.02, "spread": 0.025},
    {"name": "EURJPYc", "label": "EUR/JPY",             "digits": 3, "lot": 0.02, "spread": 0.020},
    {"name": "AUDJPYc", "label": "AUD/JPY",             "digits": 3, "lot": 0.02, "spread": 0.015},
    {"name": "CADJPYc", "label": "CAD/JPY",             "digits": 3, "lot": 0.02, "spread": 0.015},
    {"name": "CHFJPYc", "label": "CHF/JPY",             "digits": 3, "lot": 0.02, "spread": 0.025},
    {"name": "NZDJPYc", "label": "NZD/JPY",             "digits": 3, "lot": 0.02, "spread": 0.020},
    {"name": "USDJPYc", "label": "USD/JPY (Ninja)",     "digits": 3, "lot": 0.02, "spread": 0.015},

    # ── High-Volatility GBP & EUR Crosses ──
    {"name": "GBPAUDc", "label": "GBP/AUD",             "digits": 5, "lot": 0.02, "spread": 0.00025},
    {"name": "GBPCADc", "label": "GBP/CAD",             "digits": 5, "lot": 0.02, "spread": 0.00020},
    {"name": "GBPNZDc", "label": "GBP/NZD",             "digits": 5, "lot": 0.02, "spread": 0.00028},
    {"name": "GBPCHFc", "label": "GBP/CHF",             "digits": 5, "lot": 0.02, "spread": 0.00020},
    {"name": "EURAUDc", "label": "EUR/AUD",             "digits": 5, "lot": 0.02, "spread": 0.00020},
    {"name": "EURCADc", "label": "EUR/CAD",             "digits": 5, "lot": 0.02, "spread": 0.00018},
    {"name": "EURNZDc", "label": "EUR/NZD",             "digits": 5, "lot": 0.02, "spread": 0.00025},
    {"name": "EURGBPc", "label": "EUR/GBP",             "digits": 5, "lot": 0.02, "spread": 0.00015},

    # ── Commodity & Pacific Crosses ──
    {"name": "AUDCADc", "label": "AUD/CAD",             "digits": 5, "lot": 0.02, "spread": 0.00020},
    {"name": "AUDNZDc", "label": "AUD/NZD",             "digits": 5, "lot": 0.02, "spread": 0.00020},
    {"name": "AUDCHFc", "label": "AUD/CHF",             "digits": 5, "lot": 0.02, "spread": 0.00015},

    # ── Forex Majors (High Liquidity, Smooth Trends) ──
    {"name": "EURUSDc", "label": "EUR/USD (Fiber)",     "digits": 5, "lot": 0.02, "spread": 0.00012},
    {"name": "GBPUSDc", "label": "GBP/USD (Cable)",     "digits": 5, "lot": 0.02, "spread": 0.00015},
    {"name": "AUDUSDc", "label": "AUD/USD (Aussie)",    "digits": 5, "lot": 0.02, "spread": 0.00012},
    {"name": "USDCADc", "label": "USD/CAD (Loonie)",    "digits": 5, "lot": 0.02, "spread": 0.00018},
    {"name": "NZDUSDc", "label": "NZD/USD (Kiwi)",      "digits": 5, "lot": 0.02, "spread": 0.00016},
    {"name": "USDCHFc", "label": "USD/CHF (Swissy)",    "digits": 5, "lot": 0.02, "spread": 0.00015},

    # ── Crypto Asset ──
    {"name": "BTCUSDc", "label": "Bitcoin (BTC/USD)",   "digits": 2, "lot": 0.01, "spread": 8.00},
]

LOT_SIZE = {p["name"]: p["lot"] for p in ACTIVE_PAIRS}
SPREAD_USD = {p["name"]: p["spread"] for p in ACTIVE_PAIRS}
PAIR_DIGITS = {p["name"]: p["digits"] for p in ACTIVE_PAIRS}

# ── Max Layering per Pair (Hybrid AI-Grid: Layer 1 Market + Layer 2 Dip Limit) ──
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
