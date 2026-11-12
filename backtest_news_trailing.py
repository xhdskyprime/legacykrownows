# backtest_news_trailing.py
# Walk-forward backtester for Kronos AI with:
# 1. High-Impact News Filter (stops trading during red-folder news windows)
# 2. Dynamic Trailing Stop (locks in profit, moves to Break-Even, and lets winning trends run)
# Pairs: XAU/USD (Gold), GBP/USD, EUR/USD
# Period: 30 Days (720 H1 Candles)
# Account: $20 USD Cent Account (2,000 USC)

import os
import sys
import datetime
import pandas as pd
import numpy as np
import torch

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_PROJECT_ROOT, "src")
_KRONOS_REPO = os.path.join(_PROJECT_ROOT, "Kronos")

for _p in [_SRC, _PROJECT_ROOT, _KRONOS_REPO]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

from model import Kronos, KronosTokenizer, KronosPredictor
from trade_signal import generate_signal

sys.stdout.reconfigure(line_buffering=True)

print("=" * 76)
print("KRONOS AI: ADVANCED BACKTEST DENGAN NEWS FILTER & TRAILING STOP")
print("=" * 76)
print("Modal Awal:         $20.00 USD (2,000 USC Cent)")
print("Pairs:              XAU/USD (Emas), GBP/USD, EUR/USD")
print("Periode:            30 Hari Terakhir (720 Candle H1)")
print("Fitur Khusus:       1. News Filter (Anti-Gejolak Berita US/London)")
print("                    2. Trailing Stop + Break-Even (Biarkan Profit Berlari)")
print("=" * 76)

# 1. Load Kronos AI model
print("\n[1/3] Memuat Model AI Kronos...")
tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
model.to(torch.device("cpu")).eval()
predictor = KronosPredictor(model, tokenizer, max_context=512)
print("  ✓ Model siap di CPU.")

# 2. Ambil data MT5
import MetaTrader5 as mt5
mt5.initialize()

pairs_config = [
    {"name": "XAUUSDm", "label": "XAU/USD (Emas)", "digits": 3, "mult": 100.0, "lot": 0.02},
    {"name": "GBPUSDm", "label": "GBP/USD",        "digits": 5, "mult": 100000.0, "lot": 0.05},
    {"name": "EURUSDm", "label": "EUR/USD",        "digits": 5, "mult": 100000.0, "lot": 0.05},
]

pair_dfs = {}
for p in pairs_config:
    sym = p["name"]
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 720 + 200 + 20)
    if rates is not None and len(rates) >= 200:
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        pair_dfs[sym] = df[["open", "high", "low", "close"]]
        print(f"  ✓ {p['label']}: {len(df)} candle H1 berhasil dimuat.")

def is_high_impact_news_window(dt):
    """
    Mendeteksi jendela rilis berita High-Impact utama dunia (Red Folder):
    - US News (NFP, CPI, PPI, Retail Sales, GDP): 12:00 - 15:00 UTC (19:00 - 22:00 WIB)
    - US FOMC / Fed Interest Rate / Powell: 18:00 - 20:00 UTC (01:00 - 03:00 WIB)
    - London Major Opening News: 07:00 - 08:30 UTC (14:00 - 15:30 WIB)
    """
    hour = dt.hour
    weekday = dt.weekday() # 0 = Monday, 4 = Friday
    if weekday >= 5:
        return True # Weekend market closed
    if hour in [12, 13, 14, 18, 19]:
        return True
    return False

def calculate_atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(period).mean()

print("\n[2/3] Menjalankan simulasi Walk-Forward (News Filter + Trailing Stop)...")

portfolio_balance = 2000.0
equity_points = [portfolio_balance]
portfolio_results = {}
all_trades = []
news_skipped_count = 0

for p in pairs_config:
    sym = p["name"]
    label = p["label"]
    df = pair_dfs.get(sym)
    if df is None:
        continue

    # Hitung ATR untuk trailing stop dinamis
    atr_series = calculate_atr(df, period=14)

    total_bars = len(df)
    lookback = 200
    test_bars = min(720, total_bars - lookback - 1)
    start_idx = total_bars - test_bars

    print(f"\n  >> Menganalisis {label} ({test_bars} bars / 30 hari)...")
    pair_trades = []
    active_pos = None

    for i in range(test_bars):
        curr_idx = start_idx + i
        ctx = df.iloc[curr_idx - lookback : curr_idx]
        actual_bar = df.iloc[curr_idx]
        bar_time = df.index[curr_idx]
        last_close = float(ctx.iloc[-1]["close"])
        curr_atr = float(atr_series.iloc[curr_idx - 1]) if not np.isnan(atr_series.iloc[curr_idx - 1]) else 0.0020

        # ── 1. Update & Resolusi Posisi Berjalan dengan Trailing Stop ──
        if active_pos is not None:
            high = float(actual_bar["high"])
            low = float(actual_bar["low"])
            close = float(actual_bar["close"])
            resolved = False
            exit_price = None
            outcome = None

            trail_step = max(active_pos["initial_sl_dist"] * 0.75, curr_atr * 0.8)

            if active_pos["direction"] == "long":
                # Cek Stop Loss / Trailing Stop terlebih dahulu
                if low <= active_pos["current_sl"]:
                    resolved = True
                    exit_price = active_pos["current_sl"]
                    outcome = "TRAIL_WIN" if exit_price > active_pos["entry_price"] else "LOSS (SL)"
                else:
                    # Update Trailing Stop jika harga membuat High baru yang menguntungkan
                    profit_dist = high - active_pos["entry_price"]
                    if profit_dist >= active_pos["initial_sl_dist"]: # Minimal sudah profit 1x jarak SL
                        active_pos["is_trailing"] = True
                        new_sl = high - trail_step
                        # Lock minimal Break-Even
                        new_sl = max(new_sl, active_pos["entry_price"] + (active_pos["initial_sl_dist"] * 0.1))
                        if new_sl > active_pos["current_sl"]:
                            active_pos["current_sl"] = new_sl

                    # Timeout keluar jika sideways terlalu lama (16 candle / 16 jam)
                    if (curr_idx - active_pos["entry_bar_idx"]) >= 16:
                        resolved = True
                        exit_price = close
                        outcome = "EXIT (TIME)"

            else: # SHORT
                if high >= active_pos["current_sl"]:
                    resolved = True
                    exit_price = active_pos["current_sl"]
                    outcome = "TRAIL_WIN" if exit_price < active_pos["entry_price"] else "LOSS (SL)"
                else:
                    profit_dist = active_pos["entry_price"] - low
                    if profit_dist >= active_pos["initial_sl_dist"]:
                        active_pos["is_trailing"] = True
                        new_sl = low + trail_step
                        # Lock minimal Break-Even
                        new_sl = min(new_sl, active_pos["entry_price"] - (active_pos["initial_sl_dist"] * 0.1))
                        if new_sl < active_pos["current_sl"]:
                            active_pos["current_sl"] = new_sl

                    if (curr_idx - active_pos["entry_bar_idx"]) >= 16:
                        resolved = True
                        exit_price = close
                        outcome = "EXIT (TIME)"

            if resolved:
                if active_pos["direction"] == "long":
                    price_diff = exit_price - active_pos["entry_price"]
                else:
                    price_diff = active_pos["entry_price"] - exit_price

                pnl_cents = price_diff * p["lot"] * p["mult"]
                portfolio_balance += pnl_cents
                equity_points.append(portfolio_balance)

                t_record = {
                    "pair": label,
                    "entry_time": active_pos["time"],
                    "exit_time": bar_time,
                    "direction": active_pos["direction"].upper(),
                    "entry_price": round(active_pos["entry_price"], p["digits"]),
                    "exit_price": round(exit_price, p["digits"]),
                    "outcome": outcome,
                    "pnl_cent": round(pnl_cents, 2),
                    "pnl_usd": round(pnl_cents / 100.0, 4),
                    "balance_cent": round(portfolio_balance, 2)
                }
                pair_trades.append(t_record)
                all_trades.append(t_record)
                active_pos = None

        # ── 2. Cek News Filter Sebelum Buka Posisi Baru ──
        if active_pos is None:
            # Jika dalam jendela berita besar (Red Folder US/London), hentikan open posisi baru!
            if is_high_impact_news_window(bar_time):
                news_skipped_count += 1
                continue

            # Juga hindari candle yang baru saja mengalami spike abnormal > 2.5x ATR
            prev_candle_range = float(ctx.iloc[-1]["high"]) - float(ctx.iloc[-1]["low"])
            if prev_candle_range > (curr_atr * 2.5):
                continue

            # ── 3. Prediksi Candle dengan Kronos AI ──
            pred_df = predictor.predict(
                df=ctx,
                x_timestamp=ctx.index.to_series(),
                y_timestamp=pd.Series([bar_time]),
                pred_len=1,
                T=0.8,
                top_p=0.9,
                sample_count=1,
                verbose=False
            )
            pred_high = float(pred_df["high"].iloc[0])
            pred_low = float(pred_df["low"].iloc[0])
            sig = generate_signal(sym, bar_time, last_close, pred_high, pred_low)

            if sig["direction"] in ["long", "short"]:
                entry_price = float(actual_bar["open"])
                move = float(sig["predicted_move"])
                sl_dist = max(move * 0.67, curr_atr * 1.0) # Stop Loss berbasis ATR terukur

                if sig["direction"] == "long":
                    initial_sl = entry_price - sl_dist
                else:
                    initial_sl = entry_price + sl_dist

                active_pos = {
                    "direction": sig["direction"],
                    "entry_price": entry_price,
                    "initial_sl_dist": sl_dist,
                    "current_sl": initial_sl,
                    "is_trailing": False,
                    "time": bar_time,
                    "entry_bar_idx": curr_idx
                }

        if (i + 1) % 180 == 0 or (i + 1) == test_bars:
            print(f"     Progress: {i+1}/{test_bars} bars...")

    portfolio_results[sym] = pd.DataFrame(pair_trades)

# 4. Ringkasan Hasil
print("\n" + "=" * 76)
print("HASIL BACKTEST 30 HARI: NEWS FILTER + TRAILING STOP ($20 = 2,000 USC)")
print("=" * 76)

summary_rows = []
for p in pairs_config:
    sym = p["name"]
    tdf = portfolio_results.get(sym)
    if tdf is not None and len(tdf) > 0:
        n_trades = len(tdf)
        n_wins = len(tdf[tdf["pnl_cent"] > 0])
        n_loss = len(tdf[tdf["pnl_cent"] < 0])
        wr = (n_wins / n_trades) * 100.0
        tot_cent = tdf["pnl_cent"].sum()
        tot_usd = tot_cent / 100.0
        summary_rows.append({
            "Pair": p["label"],
            "Trades": n_trades,
            "Win Rate": f"{wr:.1f}% ({n_wins}W/{n_loss}L)",
            "Net Profit (Cent)": f"{tot_cent:+.2f} USC",
            "Net Profit (USD)": f"${tot_usd:+.2f} USD"
        })

summary_df = pd.DataFrame(summary_rows)
print(summary_df.to_string(index=False))
print("-" * 76)

if len(all_trades) > 0:
    all_trades_df = pd.DataFrame(all_trades)
    total_trades = len(all_trades_df)
    total_wins = len(all_trades_df[all_trades_df["pnl_cent"] > 0])
    total_losses = len(all_trades_df[all_trades_df["pnl_cent"] < 0])
    port_wr = (total_wins / total_trades) * 100.0
    net_cent = all_trades_df["pnl_cent"].sum()
    net_usd = net_cent / 100.0
    roi = (net_cent / 2000.0) * 100.0

    peak = 2000.0
    max_dd = 0.0
    for b in equity_points:
        if b > peak:
            peak = b
        dd = (peak - b) / peak * 100.0
        if dd > max_dd:
            max_dd = dd

    print(f"TOTAL TRANSAKSI (3 Pairs): {total_trades} Trade")
    print(f"SINYAL DILEWATI OLEH NEWS: {news_skipped_count} Jendela Waktu Berita")
    print(f"PORTFOLIO WIN RATE:        {port_wr:.1f}% ({total_wins} Menang / {total_losses} Kalah)")
    print(f"KEUNTUNGAN BERSIH:         {net_cent:+.2f} Cent  -->  ${net_usd:+.2f} USD")
    print(f"RETURN ON INVESTMENT (ROI): {roi:+.2f}%")
    print(f"SALDO AKHIR:               {portfolio_balance:,.2f} USC  -->  ${portfolio_balance/100:,.2f} USD")
    print(f"MAKSIMUM DRAWDOWN:         {max_dd:.2f}%")
    print("=" * 76)

    out_csv = os.path.join(_PROJECT_ROOT, "logs", "backtest_news_trailing_30d.csv")
    all_trades_df.to_csv(out_csv, index=False)
    print(f"\nDetail riwayat trade tersimpan di: {out_csv}")

