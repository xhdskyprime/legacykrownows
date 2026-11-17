# run_autopilot.py
# Production Autopilot Trading Engine for Kronos AI on MetaTrader 5.
# Fixed Setting: 10 Pairs (Majors, Crosses & Gold), Max 5 Positions per Pair,
# High-Impact News Filter, Dynamic Trailing Stop & Break-Even via KronosEA.ex5.

import os
import sys
import time
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

import MetaTrader5 as mt5
from model import Kronos, KronosTokenizer, KronosPredictor
from trade_signal import generate_signal
from execution import write_signal, read_acknowledgement
from config import (
    ACTIVE_PAIRS,
    MAX_POSITIONS_PER_PAIR,
    ENABLE_NEWS_FILTER,
    NEWS_FILTER_HOURS,
    SIGNAL_FILE,
    SIGNAL_ACK_FILE,
    MT5_COMMON_FILES
)

sys.stdout.reconfigure(line_buffering=True)
torch.set_num_threads(10)

LOG_CSV = os.path.join(_PROJECT_ROOT, "logs", "autopilot_multi_asset_live.csv")
os.makedirs(os.path.join(_PROJECT_ROOT, "logs"), exist_ok=True)


def log_event(event_dict):
    df_row = pd.DataFrame([event_dict])
    header = not os.path.exists(LOG_CSV)
    df_row.to_csv(LOG_CSV, mode="a", index=False, header=header)


def is_news_window(dt_utc):
    """Mendeteksi jendela rilis berita High-Impact utama (Red Folder)"""
    if not ENABLE_NEWS_FILTER:
        return False
    if dt_utc.weekday() >= 5: # Akhir pekan pasar tutup
        return True
    return dt_utc.hour in NEWS_FILTER_HOURS


def calculate_atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    return float(ranges.max(axis=1).rolling(period).mean().iloc[-1])


def scan_pair(predictor, pair_info):
    symbol = pair_info["name"]
    label = pair_info["label"]
    digits = pair_info["digits"]

    # 1. Pastikan simbol aktif di Market Watch MT5
    mt5.symbol_select(symbol, True)

    # Cek posisi yang sedang aktif di MT5 untuk pair ini (Khusus Magic 108888 milik bot)
    all_pos = mt5.positions_get(symbol=symbol)
    positions = [p for p in all_pos if p.magic == 108888] if all_pos is not None else []
    active_count = len(positions)

    if active_count >= MAX_POSITIONS_PER_PAIR:
        print(f"  ℹ {label:<16}: Maksimal {MAX_POSITIONS_PER_PAIR} posisi aktif tercapai ({active_count} order bot). Melewati.")
        return

    # 2. Cek News Filter
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if is_news_window(now_utc):
        print(f"  🛑 {label:<16}: Jendela berita High-Impact aktif (Jam {now_utc.hour:02d}:00 UTC). Melewati demi keamanan.")
        return

    # 3. Ambil data candle dari MT5 (dengan auto-retry jika rollover bar)
    rates = None
    for attempt in range(3):
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 250)
        if rates is not None and len(rates) >= 200:
            break
        time.sleep(1.5)
        # Jika koneksi terputus sesaat, inisialisasi ulang
        term = mt5.terminal_info()
        if term is None or not term.connected:
            mt5.initialize()

    if rates is None or len(rates) < 200:
        print(f"  ⚠ {label:<16}: Gagal mengambil data candle MT5.")
        return

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df = df[["open", "high", "low", "close"]]

    curr_atr = calculate_atr(df, period=14)
    last_candle = df.iloc[-1]
    last_candle_range = float(last_candle["high"]) - float(last_candle["low"])

    # 4. Filter lonjakan abnormal (Spike > 2.5x ATR)
    if last_candle_range > (curr_atr * 2.5):
        print(f"  ⚠ {label:<16}: Terdeteksi lonjakan harga abnormal ({last_candle_range:.{digits}f} > {curr_atr*2.5:.{digits}f}). Menunggu normalisasi.")
        return

    context = df.iloc[-200:]
    last_close = float(context.iloc[-1]["close"])
    candle_ts = context.index[-1]
    next_ts = candle_ts + datetime.timedelta(hours=1)

    # 5. Prediksi Kronos AI
    pred_df = predictor.predict(
        df=context,
        x_timestamp=context.index.to_series(),
        y_timestamp=pd.Series([next_ts]),
        pred_len=1,
        T=0.8,
        top_p=0.9,
        sample_count=2,
        verbose=False
    )

    pred_high = float(pred_df["high"].iloc[0])
    pred_low = float(pred_df["low"].iloc[0])

    signal = generate_signal(symbol, next_ts, last_close, pred_high, pred_low, atr=curr_atr)
    signal["atr"] = round(curr_atr, digits)
    direction = signal["direction"].upper()

    # Sinkronisasi SL & TP dengan harga live tick agar tidak tertolak broker (Invalid Stops)
    tick = mt5.symbol_info_tick(symbol)
    if tick is not None and signal["direction"] in ["long", "short"]:
        move = float(signal["predicted_move"])
        if signal["direction"] == "long":
            sl_dist = max(0.0, float(last_close - signal["stop_price"]))
            signal["target_price"] = round(tick.ask + move, digits)
            signal["stop_price"] = round(tick.bid - sl_dist, digits)
        else:
            sl_dist = max(0.0, float(signal["stop_price"] - last_close))
            signal["target_price"] = round(tick.bid - move, digits)
            signal["stop_price"] = round(tick.ask + sl_dist, digits)

    # 6. Cek keselarasan arah dengan posisi aktif yang sudah terbuka (Anti-Hedging)
    if active_count > 0 and signal["direction"] in ["long", "short"]:
        pos_types = [p.type for p in positions] # 0 = BUY, 1 = SELL
        if (signal["direction"] == "long" and 1 in pos_types) or (signal["direction"] == "short" and 0 in pos_types):
            print(f"  ℹ {label:<16}: Sinyal {direction} berlawanan arah dengan posisi terbuka. Melewati.")
            return

    if signal["direction"] in ["long", "short"]:
        print(f"  🎯 {label:<16}: SINYAL {direction} TERDETEKSI! (Conf: {signal['confidence']:.1%}, TP: {signal['target_price']:.{digits}f}, SL: {signal['stop_price']:.{digits}f}, Lot: {signal['lot_size']})")
        print(f"     >> Mengirimkan sinyal ke KronosEA di MT5...")
        write_signal(signal)
        ack = read_acknowledgement(timeout_seconds=20)
        if ack:
            print(f"     ✓ Order {direction} berhasil dieksekusi MT5! Respon: {ack}")
            log_event({
                "time": str(datetime.datetime.now()),
                "symbol": symbol,
                "direction": direction,
                "price": last_close,
                "tp": signal["target_price"],
                "sl": signal["stop_price"],
                "lot": signal["lot_size"],
                "status": "EXECUTED",
                "ack": str(ack)
            })
        else:
            print(f"     ⚠ Tidak ada konfirmasi dari MT5 EA dalam 20 detik.")
    else:
        print(f"  ℹ {label:<16}: Tidak ada sinyal (FLAT / Spread Filter).")


def main():
    print("=" * 78)
    print("KRONOS HYBRID AI-GRID v3.0 - PRODUCTION ENGINE")
    print("=" * 78)

    if not mt5.initialize():
        print(f"Gagal menghubungkan ke MetaTrader 5: {mt5.last_error()}")
        sys.exit(1)

    acc = mt5.account_info()
    print(f"Akun MT5:          Login {acc.login} ({acc.server})")
    print(f"Saldo:             ${acc.balance:,.2f} {acc.currency}")
    print(f"Jumlah Pair:       {len(ACTIVE_PAIRS)} Pair Aktif")
    print(f"Maksimal Layer:    {MAX_POSITIONS_PER_PAIR} Layer (Hybrid AI-Grid: Market L1 + Dip Limit L2)")
    print(f"Basket Close:      Aktif di MT5 (Auto Close Keranjang saat Target Profit Tercapai)")
    print(f"Trailing Stop:     Aktif di MT5 (Lock BEP + Trail Single Moves)")
    print(f"News Filter:       {'Aktif' if ENABLE_NEWS_FILTER else 'Mati (24/7 Trading)'}")
    print("-" * 78)

    print("\nMemuat Model AI Kronos...")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    model.to(torch.device("cpu")).eval()
    predictor = KronosPredictor(model, tokenizer, max_context=512)
    print("✓ Model Kronos AI siap di CPU (10 threads).")

    print(f"\nMemulai pemindaian {len(ACTIVE_PAIRS)} pair secara live...")
    last_processed_hour = -1

    while True:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if now_utc.hour != last_processed_hour:
                print(f"\n" + "=" * 78)
                print(f"SIKLUS PEMINDAIAN BARU: UTC {now_utc.strftime('%Y-%m-%d %H:%M:%S')} (WIB {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
                print("=" * 78)

                for p in ACTIVE_PAIRS:
                    scan_pair(predictor, p)
                    time.sleep(2) # Jeda aman 2 detik antar pair

                last_processed_hour = now_utc.hour

            # Cek setiap 15 detik
            time.sleep(15)

        except KeyboardInterrupt:
            print("\nAutopilot dihentikan oleh pengguna.")
            break
        except Exception as e:
            print(f"\nError pada siklus: {e}")
            time.sleep(10)

    mt5.shutdown()


if __name__ == "__main__":
    main()
