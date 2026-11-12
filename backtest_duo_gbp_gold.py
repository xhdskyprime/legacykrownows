# backtest_duo_gbp_gold.py
# Walk-forward backtest for the recommended "Golden Duo" portfolio:
# GBP/USD (Top Forex Volatility) + XAU/USD (Gold - King of Volatility)
# Capital: $20.00 USD (= 2,000 USC Cent Account)
# Timeframe: H1 (1 Hour), 30 Days

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

print("=" * 72)
print("KRONOS AI PORTFOLIO BACKTEST: GBP/USD + XAU/USD (GOLD)")
print("Modal Awal:         $20.00 USD (2,000 USC Cent)")
print("Pairs:              GBP/USD + XAU/USD (Emas)")
print("Periode:            30 Hari Terakhir (720 Candle H1)")
print("Ukuran Lot:         0.05 Cent Lot (GBP) & 0.02 Cent Lot (Gold)")
print("=" * 72)

# 1. Load model
print("\n[1/3] Memuat Model AI Kronos...")
tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
model.to(torch.device("cpu")).eval()
predictor = KronosPredictor(model, tokenizer, max_context=512)
print("  ✓ Model siap di CPU.")

# 2. Fetch MT5 Data
import MetaTrader5 as mt5
mt5.initialize()

pairs_config = [
    {"name": "GBPUSDm", "label": "GBP/USD", "digits": 5, "mult": 100000.0, "lot": 0.05},
    {"name": "XAUUSDm", "label": "XAU/USD (Gold)", "digits": 3, "mult": 100.0, "lot": 0.02}, # 0.02 lot cent on gold: $1 move = 2 USC ($0.02)
]

pair_dfs = {}
for p in pairs_config:
    sym = p["name"]
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 720 + 200 + 10)
    if rates is not None and len(rates) >= 200:
        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        pair_dfs[sym] = df[["open", "high", "low", "close"]]
        print(f"  ✓ {p['label']}: {len(df)} candle H1 berhasil dimuat.")

print("\n[2/3] Menjalankan simulasi Walk-Forward...")
portfolio_balance = 2000.0
equity_points = [portfolio_balance]
portfolio_results = {}
all_trades = []

for p in pairs_config:
    sym = p["name"]
    label = p["label"]
    df = pair_dfs.get(sym)
    if df is None:
        continue

    total_bars = len(df)
    lookback = 200
    test_bars = min(720, total_bars - lookback - 1)
    start_idx = total_bars - test_bars

    print(f"\n  >> Menganalisis {label} ({test_bars} bars)...")
    pair_trades = []
    active_pos = None

    for i in range(test_bars):
        curr_idx = start_idx + i
        ctx = df.iloc[curr_idx - lookback : curr_idx]
        actual_bar = df.iloc[curr_idx]
        bar_time = df.index[curr_idx]
        last_close = float(ctx.iloc[-1]["close"])

        if active_pos is not None:
            high = float(actual_bar["high"])
            low = float(actual_bar["low"])
            close = float(actual_bar["close"])
            resolved = False
            exit_price = None
            outcome = None

            if active_pos["direction"] == "long":
                if low <= active_pos["sl"]:
                    resolved = True
                    exit_price = active_pos["sl"]
                    outcome = "LOSS (SL)"
                elif high >= active_pos["tp"]:
                    resolved = True
                    exit_price = active_pos["tp"]
                    outcome = "WIN (TP)"
                elif (curr_idx - active_pos["entry_bar_idx"]) >= 12:
                    resolved = True
                    exit_price = close
                    outcome = "EXIT (TIME)"
            else:
                if high >= active_pos["sl"]:
                    resolved = True
                    exit_price = active_pos["sl"]
                    outcome = "LOSS (SL)"
                elif low <= active_pos["tp"]:
                    resolved = True
                    exit_price = active_pos["tp"]
                    outcome = "WIN (TP)"
                elif (curr_idx - active_pos["entry_bar_idx"]) >= 12:
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

        if active_pos is None:
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
                sl_dist = move * 0.67
                if sig["direction"] == "long":
                    tp = entry_price + move
                    sl = entry_price - sl_dist
                else:
                    tp = entry_price - move
                    sl = entry_price + sl_dist

                active_pos = {
                    "direction": sig["direction"],
                    "entry_price": entry_price,
                    "tp": tp,
                    "sl": sl,
                    "time": bar_time,
                    "entry_bar_idx": curr_idx
                }

        if (i + 1) % 180 == 0 or (i + 1) == test_bars:
            print(f"     Progress: {i+1}/{test_bars} bars...")

    portfolio_results[sym] = pd.DataFrame(pair_trades)

print("\n" + "=" * 72)
print("HASIL KOMBINASI GBP/USD + XAU/USD (GOLD) - 30 HARI")
print("=" * 72)

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
print("-" * 72)

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

    print(f"TOTAL TRANSAKSI:           {total_trades} Trade")
    print(f"PORTFOLIO WIN RATE:        {port_wr:.1f}% ({total_wins} Menang / {total_losses} Kalah)")
    print(f"KEUNTUNGAN BERSIH:         {net_cent:+.2f} Cent  -->  ${net_usd:+.2f} USD")
    print(f"RETURN ON INVESTMENT (ROI): {roi:+.2f}%")
    print(f"SALDO AKHIR:               {portfolio_balance:,.2f} USC  -->  ${portfolio_balance/100:,.2f} USD")
    print(f"MAKSIMUM DRAWDOWN:         {max_dd:.2f}%")
    print("=" * 72)

