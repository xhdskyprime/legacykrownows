# run_autopilot.py
# Production Autopilot Trading Engine for Kronos AI on MetaTrader 5.
# Dual-Mode Live A/B Testing Edition v3.2:
#   - Mode B (Magic 108882): Smart R:R (pred_len=3, Conf >= 65%, TP >= 1.25x SL)
#   - Mode C (Magic 108883): Smart R:R + EMA50 Trend Alignment
# Both modes run simultaneously on 28 active Cent pairs with full manual trade isolation (Magic 0 untouched)
# and identical Stepped Trailing Stop (0.5 ATR BEP -> Tiered Profit Locks) inside KronosEA.ex5.

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
from trade_signal import generate_dual_signals
from execution import write_signal, read_acknowledgement
from config import (
    ACTIVE_PAIRS,
    MAX_POSITIONS_PER_PAIR,
    ENABLE_NEWS_FILTER,
    NEWS_FILTER_HOURS,
)

sys.stdout.reconfigure(line_buffering=True)
torch.set_num_threads(10)

MAGIC_MODE_B = 108882
MAGIC_MODE_C = 108883

LOG_CSV = os.path.join(_PROJECT_ROOT, "logs", "autopilot_dual_ab_live.csv")
os.makedirs(os.path.join(_PROJECT_ROOT, "logs"), exist_ok=True)


def log_event(event_dict):
    df_row = pd.DataFrame([event_dict])
    header = not os.path.exists(LOG_CSV)
    df_row.to_csv(LOG_CSV, mode="a", index=False, header=header)


def is_news_window(dt_utc):
    if not ENABLE_NEWS_FILTER:
        return False
    if dt_utc.weekday() >= 5:
        return True
    return dt_utc.hour in NEWS_FILTER_HOURS


def calculate_atr(df, period=14):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    return float(ranges.max(axis=1).rolling(period).mean().iloc[-1])


def dispatch_mode_signal(symbol, label, digits, signal, mode_name, mode_magic, all_pos):
    if signal["direction"] not in ("long", "short"):
        return False

    mode_pos = [p for p in all_pos if p.magic == mode_magic] if all_pos is not None else []
    active_count = len(mode_pos)
    direction = signal["direction"].upper()

    if active_count >= MAX_POSITIONS_PER_PAIR:
        print(f"    ℹ [{mode_name}] {label:<16}: Maksimal {MAX_POSITIONS_PER_PAIR} posisi tercapai. Lewati.")
        return False

    # Anti-Hedging khusus dalam mode ini saja
    if active_count > 0:
        pos_types = [p.type for p in mode_pos]  # 0 = BUY, 1 = SELL
        if (signal["direction"] == "long" and 1 in pos_types) or (signal["direction"] == "short" and 0 in pos_types):
            print(f"    ℹ [{mode_name}] {label:<16}: Sinyal {direction} berlawanan arah dengan posisi {mode_name}. Lewati.")
            return False

    # Sinkronisasi SL & TP dengan live tick agar bebas Invalid Stops
    tick = mt5.symbol_info_tick(symbol)
    if tick is not None:
        move = float(signal["predicted_move"])
        sl_dist = float(signal["sl_distance"])
        if signal["direction"] == "long":
            signal["target_price"] = round(tick.ask + move, digits)
            signal["stop_price"] = round(tick.bid - sl_dist, digits)
        else:
            signal["target_price"] = round(tick.bid - move, digits)
            signal["stop_price"] = round(tick.ask + sl_dist, digits)

    print(
        f"  🎯 [{mode_name}] {label:<16}: {direction:<5} "
        f"(Conf: {signal['confidence']:.1%}, TP: {signal['target_price']:.{digits}f}, "
        f"SL: {signal['stop_price']:.{digits}f}, Lot: {signal['lot_size']})"
    )
    write_signal(signal)
    ack = read_acknowledgement(timeout_seconds=15)
    if ack:
        print(f"     ✓ [{mode_name}] Order {direction} dieksekusi MT5 (Magic {mode_magic})!")
        log_event({
            "time": str(datetime.datetime.now()),
            "mode": mode_name,
            "magic": mode_magic,
            "symbol": symbol,
            "direction": direction,
            "confidence": signal["confidence"],
            "tp": signal["target_price"],
            "sl": signal["stop_price"],
            "lot": signal["lot_size"],
            "status": "EXECUTED",
        })
        return True
    else:
        print(f"     ⚠ [{mode_name}] Tidak ada konfirmasi dari MT5 EA dalam 15 detik.")
        return False


def scan_pair(predictor, pair_info):
    symbol = pair_info["name"]
    label = pair_info["label"]
    digits = pair_info["digits"]

    mt5.symbol_select(symbol, True)

    all_pos = mt5.positions_get(symbol=symbol)
    cnt_b = len([p for p in all_pos if p.magic == MAGIC_MODE_B]) if all_pos is not None else 0
    cnt_c = len([p for p in all_pos if p.magic == MAGIC_MODE_C]) if all_pos is not None else 0

    if cnt_b >= MAX_POSITIONS_PER_PAIR and cnt_c >= MAX_POSITIONS_PER_PAIR:
        print(f"  ℹ {label:<16}: Slot Mode B ({cnt_b}) & Mode C ({cnt_c}) penuh. Melewati.")
        return

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if is_news_window(now_utc):
        print(f"  🛑 {label:<16}: Jendela berita High-Impact aktif. Melewati.")
        return

    rates = None
    for _ in range(3):
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, 250)
        if rates is not None and len(rates) >= 200:
            break
        time.sleep(1.5)
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
    ema50 = float(df["close"].ewm(span=50, adjust=False).mean().iloc[-1])

    last_candle = df.iloc[-1]
    last_candle_range = float(last_candle["high"]) - float(last_candle["low"])

    if last_candle_range > (curr_atr * 2.5):
        print(f"  ⚠ {label:<16}: Lonjakan harga abnormal (> 2.5x ATR). Menunggu normalisasi.")
        return

    context = df.iloc[-200:]
    last_close = float(context.iloc[-1]["close"])
    candle_ts = context.index[-1]
    y_ts = pd.Series([
        candle_ts + datetime.timedelta(hours=1),
        candle_ts + datetime.timedelta(hours=2),
        candle_ts + datetime.timedelta(hours=3),
    ])

    # Satu kali prediksi Kronos AI (horizon 3 jam) untuk kedua mode B & C
    pred_df = predictor.predict(
        df=context,
        x_timestamp=context.index.to_series(),
        y_timestamp=y_ts,
        pred_len=3,
        T=0.8,
        top_p=0.9,
        sample_count=2,
        verbose=False,
    )

    pred_high_3 = float(pred_df["high"].max())
    pred_low_3 = float(pred_df["low"].min())

    dual = generate_dual_signals(symbol, y_ts.iloc[0], last_close, pred_high_3, pred_low_3, atr=curr_atr, ema50=ema50)
    sig_b = dual["mode_b"]
    sig_c = dual["mode_c"]

    if sig_b["direction"] == "flat" and sig_c["direction"] == "flat":
        trend_lbl = "UP" if last_close >= ema50 else "DN"
        print(f"  · {label:<16}: Tidak lolos filter Smart R:R / Conf>=65% (Trend EMA50: {trend_lbl}).")
        return

    # Kirim Mode B (108882) jika aktif
    if sig_b["direction"] in ("long", "short"):
        dispatch_mode_signal(symbol, label, digits, sig_b, "ModeB", MAGIC_MODE_B, all_pos)
        time.sleep(0.8)

    # Kirim Mode C (108883) jika juga lolos filter EMA50
    if sig_c["direction"] in ("long", "short"):
        dispatch_mode_signal(symbol, label, digits, sig_c, "ModeC", MAGIC_MODE_C, all_pos)
    else:
        print(f"    ↳ [ModeC] {label:<16}: Ditahan filter EMA50 (berlawanan tren utama).")


def main():
    print("=" * 78)
    print("KRONOS DUAL-MODE A/B v3.2 (MODE B vs MODE C) - PRODUCTION ENGINE")
    print("=" * 78)

    if not mt5.initialize():
        print(f"Gagal menghubungkan ke MetaTrader 5: {mt5.last_error()}")
        sys.exit(1)

    acc = mt5.account_info()
    print(f"Akun MT5:          Login {acc.login} ({acc.server})")
    print(f"Saldo:             ${acc.balance:,.2f} {acc.currency}")
    print(f"Jumlah Pair:       {len(ACTIVE_PAIRS)} Pair Aktif (Termasuk XAUUSDc)")
    print(f"Horizon AI:        3 Jam (pred_len=3) | Filter Conf >= 65% | TP >= 1.25x SL")
    print(f"Mode B (108882):   Smart R:R (Tanpa filter tren EMA50)")
    print(f"Mode C (108883):   Smart R:R + Filter Tren EMA50 (Searah Tren Utama)")
    print(f"Isolasi Manual:    Aktif (Trade manual Magic 0 100% aman & tidak disentuh)")
    print(f"Trailing Stop:     Stepped Trailing di MT5 (0.5 ATR BEP -> Tangga Profit)")
    print(f"News Filter:       {'Aktif' if ENABLE_NEWS_FILTER else 'Mati (24/7 Trading)'}")
    print("-" * 78)

    print("\nMemuat Model AI Kronos...")
    tokenizer = KronosTokenizer.from_pretrained("NeoQuasar/Kronos-Tokenizer-base")
    model = Kronos.from_pretrained("NeoQuasar/Kronos-small")
    model.to(torch.device("cpu")).eval()
    predictor = KronosPredictor(model, tokenizer, max_context=512)
    print("✓ Model Kronos AI siap di CPU (10 threads).")

    print(f"\nMemulai pemindaian Dual-Mode A/B di {len(ACTIVE_PAIRS)} pair secara live...")
    last_processed_hour = -1

    while True:
        try:
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            if now_utc.hour != last_processed_hour:
                print("\n" + "=" * 78)
                print(
                    f"SIKLUS PEMINDAIAN DUAL-MODE BARU: UTC {now_utc.strftime('%Y-%m-%d %H:%M:%S')} "
                    f"(WIB {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
                )
                print("=" * 78)

                for p in ACTIVE_PAIRS:
                    scan_pair(predictor, p)
                    time.sleep(1.5)

                last_processed_hour = now_utc.hour

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
