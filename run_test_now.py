# run_test_now.py
# Immediate single-cycle test script for Kronos Trading System on Windows / MT5.
# Runs 1 prediction immediately on chosen symbol (XAUUSDm, BTCUSDm, etc.)

import os
import sys
import datetime
import argparse
import pandas as pd
import yfinance as yf
import torch

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_PROJECT_ROOT, "src")
_KRONOS_REPO = os.path.join(_PROJECT_ROOT, "Kronos")

for _p in [_SRC, _PROJECT_ROOT, _KRONOS_REPO]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from model import Kronos, KronosTokenizer, KronosPredictor
from trade_signal import generate_signal
from execution import write_signal, read_acknowledgement
from config import SIGNAL_FILE, SIGNAL_ACK_FILE, MT5_COMMON_FILES

parser = argparse.ArgumentParser(description="Kronos 1-Cycle Test")
parser.add_argument("--symbol", type=str, default="XAUUSDm", help="Target symbol (e.g. XAUUSDm, BTCUSDm)")
args = parser.parse_args()
symbol = args.symbol

print("\n" + "=" * 60)
print(f"KRONOS AI TRADING - 1-CYCLE IMMEDIATE DEMO TEST [{symbol}]")
print("=" * 60)
print(f"Target Symbol:        {symbol}")
print(f"MT5 Common Files:     {MT5_COMMON_FILES}")
print(f"Signal Path:          {SIGNAL_FILE}")
print("-" * 60)

# 1. Load Kronos model
print("\n[1/4] Loading Kronos AI model...")
tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
model.to(torch.device("cpu")).eval()
predictor = KronosPredictor(model, tokenizer, max_context=512)
print("  ✓ Model loaded on CPU successfully")

# 2. Fetch candle data
print(f"\n[2/4] Fetching latest market data for {symbol}...")
df = None
import MetaTrader5 as mt5
if mt5.initialize():
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 250)
    if rates is not None and len(rates) >= 200:
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        df = df[["open", "high", "low", "close"]]
        print(f"  ✓ Fetched {len(df)} candles directly from MT5 terminal ({symbol})")

if df is None:
    yf_ticker = "GC=F" if "XAU" in symbol else "BTC-USD"
    print(f"  Notice: Fetching from Yahoo Finance ({yf_ticker})...")
    raw = yf.download(yf_ticker, period="30d", interval="1h", progress=False)
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.columns = [c.lower() for c in raw.columns]
    df = raw[["open", "high", "low", "close"]].dropna()
    try:
        if df.index.tz is not None:
            df.index = df.index.tz_convert(None)
    except Exception:
        df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)

lookback = min(200, len(df) - 1)
context = df.iloc[-lookback:]
last_close = float(context.iloc[-1]["close"])
next_candle_ts = context.index[-1] + datetime.timedelta(hours=1)
dec = 5 if ("EUR" in symbol or "GBP" in symbol or "AUD" in symbol) else (3 if ("XAU" in symbol or "JPY" in symbol) else 2)
print(f"  ✓ Latest candle close: {last_close:.{dec}f} ({context.index[-1]})")

# 3. Predict next candle
print("\n[3/4] Running Kronos AI inference (Monte Carlo)...")
pred_df = predictor.predict(
    df=context,
    x_timestamp=context.index.to_series(),
    y_timestamp=pd.Series([next_candle_ts]),
    pred_len=1,
    T=0.8,
    top_p=0.9,
    sample_count=4,
    verbose=False
)

pred_high = float(pred_df["high"].iloc[0])
pred_low = float(pred_df["low"].iloc[0])
pred_close = float(pred_df["close"].iloc[0])

signal = generate_signal(symbol, next_candle_ts, last_close, pred_high, pred_low)
print(f"  ✓ AI Forecast: High={pred_high:.{dec}f} | Low={pred_low:.{dec}f} | Close={pred_close:.{dec}f}")
print(f"  ✓ Decision:    {signal['direction'].upper()} (Confidence: {signal['confidence']:.1%})")
if signal['direction'] != 'flat':
    print(f"  ✓ Take Profit: {signal['target_price']:.{dec}f}")
    print(f"  ✓ Stop Loss:   {signal['stop_price']:.{dec}f}")
    print(f"  ✓ Lot Size:    {signal['lot_size']}")

# 4. Send signal to MT5 EA
print("\n[4/4] Sending signal to MT5 EA via file bridge...")
write_signal(signal)
print(f"  ✓ Sinyal ditulis ke: {SIGNAL_FILE}")
print(f"  >> Menunggu respon dari KronosEA di MT5 untuk {symbol} (maksimal 30 detik)...")

ack = read_acknowledgement(timeout_seconds=30)
if ack:
    print("\n" + "=" * 60)
    print(f"✓ SUKSES! KronosEA di MT5 telah menerima dan mengeksekusi order {symbol}!")
    print("=" * 60)
else:
    print("\n" + "-" * 60)
    print("Catatan: Belum ada respon dari EA dalam 30 detik.")
    print(f"Pastikan KronosEA terpasang di chart {symbol} atau chart manapun dengan Algo Trading AKTIF.")
    print("-" * 60)
