# backtest.py
# Walk-forward backtester for Kronos AI Trading System.
# Simulates live AI trading performance over historical data (e.g., past 30 days).

import os
import sys
import datetime
import pandas as pd
import numpy as np
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
from config import SPREAD_USD, SPREAD_MULTIPLIER

def run_backtest(ticker="BTC-USD", symbol_name="BTCUSDm", timeframe="1h", days=30, initial_balance=500.0, lot_size=0.01):
    print("=" * 65)
    print(f"KRONOS AI HISTORICAL BACKTEST (Past {days} Days)")
    print("=" * 65)
    print(f"Ticker:            {ticker} ({symbol_name})")
    print(f"Timeframe:         {timeframe}")
    print(f"Initial Balance:   ${initial_balance:,.2f}")
    print(f"Lot Size:          {lot_size}")
    print("-" * 65)

    # 1. Load Kronos model
    print("\n[1/3] Loading Kronos AI model...")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    model.to(torch.device("cpu")).eval()
    predictor = KronosPredictor(model, tokenizer, max_context=512)
    print("  ✓ Model ready.")

    # 2. Download historical data directly from MT5 (or yfinance fallback)
    print(f"\n[2/3] Fetching historical market data ({days} days)...")
    bars_needed = days * (24 if timeframe == '1h' else 6) + 250
    df = None

    contract_size = 1.0
    import MetaTrader5 as mt5
    if mt5.initialize():
        s_info = mt5.symbol_info(symbol_name)
        if s_info:
            contract_size = s_info.trade_contract_size
        tf_code = mt5.TIMEFRAME_H1 if timeframe == '1h' else mt5.TIMEFRAME_H4
        rates = mt5.copy_rates_from_pos(symbol_name, tf_code, 0, bars_needed)
        if rates is not None and len(rates) > 200:
            df = pd.DataFrame(rates)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            df.set_index("time", inplace=True)
            df = df[["open", "high", "low", "close"]]
            print(f"  ✓ Fetched {len(df)} candles directly from MetaTrader 5 ({symbol_name})")
    elif "XAU" in symbol_name:
        contract_size = 100.0

    if df is None or len(df) < 200:
        print("  Notice: MT5 fetch returned insufficient data, falling back to Yahoo Finance...")
        raw = yf.download(ticker, period="60d", interval=timeframe, progress=False)
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        raw.columns = [c.lower() for c in raw.columns]
        df = raw[["open", "high", "low", "close"]].dropna()
        try:
            if df.index.tz is not None:
                df.index = df.index.tz_convert(None)
        except Exception:
            df.index = pd.to_datetime(df.index, utc=True).tz_localize(None)

    total_bars = len(df)
    lookback = 200
    test_bars = min(total_bars - lookback - 1, days * (24 if timeframe == '1h' else 6))

    if test_bars <= 0:
        print(f"Error: Not enough bars downloaded ({total_bars} bars).")
        return

    start_idx = total_bars - test_bars
    test_start_date = df.index[start_idx]
    test_end_date = df.index[-1]
    print(f"  ✓ Data ready: {test_bars} bars to simulate from {test_start_date} to {test_end_date}")

    # 3. Walk-Forward Simulation
    print(f"\n[3/3] Simulating Kronos AI walk-forward trading ({test_bars} bars)...")
    
    trades = []
    active_position = None
    balance = initial_balance
    equity_curve = [balance]

    # Pre-extract numpy arrays for fast lookback slicing
    for i in range(test_bars):
        curr_idx = start_idx + i
        ctx = df.iloc[curr_idx - lookback : curr_idx]
        actual_bar = df.iloc[curr_idx]
        bar_time = df.index[curr_idx]

        last_close = float(ctx.iloc[-1]["close"])
        target_ts = pd.Series([bar_time])
        ctx_ts = ctx.index.to_series()

        # Check existing open position resolution first
        if active_position is not None:
            pos = active_position
            pos_high = float(actual_bar["high"])
            pos_low = float(actual_bar["low"])
            pos_close = float(actual_bar["close"])
            resolved = False
            exit_price = None
            outcome = None

            if pos["direction"] == "long":
                if pos_low <= pos["sl"]:
                    resolved = True
                    exit_price = pos["sl"]
                    outcome = "LOSS (SL)"
                elif pos_high >= pos["tp"]:
                    resolved = True
                    exit_price = pos["tp"]
                    outcome = "WIN (TP)"
                elif (curr_idx - pos["entry_bar_idx"]) >= 12: # Time-exit after 12 bars
                    resolved = True
                    exit_price = pos_close
                    outcome = "EXIT (TIME)"
            elif pos["direction"] == "short":
                if pos_high >= pos["sl"]:
                    resolved = True
                    exit_price = pos["sl"]
                    outcome = "LOSS (SL)"
                elif pos_low <= pos["tp"]:
                    resolved = True
                    exit_price = pos["tp"]
                    outcome = "WIN (TP)"
                elif (curr_idx - pos["entry_bar_idx"]) >= 12:
                    resolved = True
                    exit_price = pos_close
                    outcome = "EXIT (TIME)"

            if resolved:
                if pos["direction"] == "long":
                    pnl = (exit_price - pos["entry_price"]) * lot_size * contract_size
                else:
                    pnl = (pos["entry_price"] - exit_price) * lot_size * contract_size

                balance += pnl
                equity_curve.append(balance)
                trades.append({
                    "entry_time": pos["time"],
                    "exit_time": bar_time,
                    "direction": pos["direction"].upper(),
                    "entry_price": round(pos["entry_price"], 2),
                    "exit_price": round(exit_price, 2),
                    "outcome": outcome,
                    "pnl": round(pnl, 2),
                    "balance": round(balance, 2)
                })
                active_position = None

        # Predict next bar with Kronos
        pred_df = predictor.predict(
            df=ctx,
            x_timestamp=ctx_ts,
            y_timestamp=target_ts,
            pred_len=1,
            T=0.8,
            top_p=0.9,
            sample_count=2,
            verbose=False
        )

        pred_high = float(pred_df["high"].iloc[0])
        pred_low = float(pred_df["low"].iloc[0])

        sig = generate_signal(symbol_name, bar_time, last_close, pred_high, pred_low)

        # Enter position if no position active and direction is long/short
        if active_position is None and sig["direction"] in ["long", "short"]:
            entry_price = float(actual_bar["open"])
            move = float(sig["predicted_move"])
            sl_dist = move * 0.67
            if sig["direction"] == "long":
                tp = entry_price + move
                sl = entry_price - sl_dist
            else:
                tp = entry_price - move
                sl = entry_price + sl_dist

            active_position = {
                "direction": sig["direction"],
                "entry_price": entry_price,
                "tp": tp,
                "sl": sl,
                "time": bar_time,
                "entry_bar_idx": curr_idx
            }

        if (i + 1) % 20 == 0 or (i + 1) == test_bars:
            print(f"  Processed {i + 1}/{test_bars} bars... (Current Trades: {len(trades)}, Balance: ${balance:,.2f})")

    # 4. Compile Metrics
    print("\n" + "=" * 65)
    print("BACKTEST RESULTS SUMMARY")
    print("=" * 65)

    if not trades:
        print("No trades triggered during this period (spread filter or no signals).")
        return

    trades_df = pd.DataFrame(trades)
    total_trades = len(trades_df)
    wins = trades_df[trades_df["pnl"] > 0]
    losses = trades_df[trades_df["pnl"] < 0]
    win_rate = (len(wins) / total_trades) * 100 if total_trades > 0 else 0
    total_profit = wins["pnl"].sum()
    total_loss = abs(losses["pnl"].sum())
    profit_factor = (total_profit / total_loss) if total_loss > 0 else 99.0
    net_pnl = trades_df["pnl"].sum()
    pct_return = (net_pnl / initial_balance) * 100

    peak = initial_balance
    max_dd = 0.0
    for b in equity_curve:
        if b > peak:
            peak = b
        dd = (peak - b) / peak * 100
        if dd > max_dd:
            max_dd = dd

    print(f"Period:              {test_start_date.strftime('%Y-%m-%d')} s/d {test_end_date.strftime('%Y-%m-%d')}")
    print(f"Total Trades:        {total_trades}")
    print(f"Win Trades:          {len(wins)} ({win_rate:.1f}%)")
    print(f"Loss Trades:         {len(losses)} ({100 - win_rate:.1f}%)")
    print(f"Net Profit/Loss:     ${net_pnl:+,.2f} ({pct_return:+.2f}%)")
    print(f"Final Balance:       ${balance:,.2f}")
    print(f"Profit Factor:       {profit_factor:.2f}")
    print(f"Max Drawdown:        {max_dd:.2f}%")
    print("-" * 65)

    os.makedirs(os.path.join(_PROJECT_ROOT, "logs"), exist_ok=True)
    out_csv = os.path.join(_PROJECT_ROOT, "logs", f"backtest_{days}d_{ticker.replace('-', '_')}.csv")
    trades_df.to_csv(out_csv, index=False)
    print(f"Detailed trade log saved to:\n  {out_csv}\n")

    print("Sample Trades (Last 5):")
    print(trades_df.tail(5).to_string(index=False))
    print("=" * 65)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Kronos AI Backtester")
    parser.add_argument("--days", type=int, default=30, help="Number of past days to test (default: 30)")
    parser.add_argument("--ticker", type=str, default="BTC-USD", help="Ticker symbol (default: BTC-USD)")
    parser.add_argument("--symbol", type=str, default="BTCUSDm", help="MT5 Symbol name (default: BTCUSDm)")
    parser.add_argument("--tf", type=str, default="1h", help="Timeframe (default: 1h)")
    args = parser.parse_args()

    run_backtest(ticker=args.ticker, symbol_name=args.symbol, timeframe=args.tf, days=args.days)
