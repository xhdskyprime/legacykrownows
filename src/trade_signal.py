# trade_signal.py
# Signal generation layer for Kronos trading system (10-Pair Mega Setup).
# Translates Kronos candle predictions into actionable trade signals (long / short / flat)
# with dynamic Stop Loss and Take Profit levels according to risk management rules.

from config import SPREAD_USD, SPREAD_MULTIPLIER, LOT_SIZE, PAIR_DIGITS

def generate_signal(pair, timestamp, last_close, pred_high, pred_low, atr=None):
    """
    Generate a trading signal based on predicted high and low compared to the last close.

    Rules:
      - Upside move = pred_high - last_close
      - Downside move = last_close - pred_low
      - Filter: Expected move must exceed broker spread * SPREAD_MULTIPLIER
      - Risk Management: 1:1.5 reward/risk ratio with ATR safety buffer
    """
    digits = PAIR_DIGITS.get(pair, 5 if "JPY" not in pair and "XAU" not in pair else 3)
    default_spread = 0.50 if "XAU" in pair else (0.02 if "JPY" in pair else 0.0002)
    spread = SPREAD_USD.get(pair, default_spread)
    min_required_move = spread * SPREAD_MULTIPLIER

    upside_move = max(0.0, pred_high - last_close)
    downside_move = max(0.0, last_close - pred_low)

    lot = LOT_SIZE.get(pair, 0.01)

    if upside_move > downside_move and upside_move >= min_required_move:
        direction = "long"
        predicted_move = round(upside_move, digits)
        target_price = round(pred_high, digits)
        sl_distance = max(spread * 2.0, upside_move * 0.67)
        if atr is not None and atr > 0:
            sl_distance = max(sl_distance, atr * 0.8)
        stop_price = round(last_close - sl_distance, digits)
        confidence = min(0.95, max(0.55, upside_move / (upside_move + downside_move + 1e-6)))
        spread_filter = True
    elif downside_move > upside_move and downside_move >= min_required_move:
        direction = "short"
        predicted_move = round(downside_move, digits)
        target_price = round(pred_low, digits)
        sl_distance = max(spread * 2.0, downside_move * 0.67)
        if atr is not None and atr > 0:
            sl_distance = max(sl_distance, atr * 0.8)
        stop_price = round(last_close + sl_distance, digits)
        confidence = min(0.95, max(0.55, downside_move / (upside_move + downside_move + 1e-6)))
        spread_filter = True
    else:
        direction = "flat"
        predicted_move = 0.0
        target_price = None
        stop_price = None
        confidence = 0.0
        lot = 0.0
        spread_filter = False

    return {
        "pair":           pair,
        "timestamp":      str(timestamp),
        "direction":      direction,
        "confidence":     round(confidence, 4),
        "predicted_high": round(pred_high, digits),
        "predicted_low":  round(pred_low, digits),
        "target_price":   target_price,
        "stop_price":     stop_price,
        "predicted_move": predicted_move,
        "lot_size":       lot,
        "spread_filter":  spread_filter,
    }


def generate_dual_signals(pair, timestamp, last_close, pred_high_3, pred_low_3, atr, ema50):
    """
    Generate simultaneous Mode B (Smart R:R, 3h horizon) and Mode C (Smart R:R + EMA50 Trend) signals
    for live A/B comparison on isolated Magic Numbers (Mode B = 108882, Mode C = 108883).

    Rules (validated in 5-day walk-forward H1 backtest):
      - Horizon: 3 H1 candles (max predicted high, min predicted low)
      - Confidence >= 65%
      - Minimum move >= max(spread * 2.5, atr * 0.9)
      - TP capped at 2.2 * ATR, SL = max(spread * 2.5, atr * 0.85)
      - Strict R:R gate: TP >= 1.25 * SL
      - Mode B (108882): fires when Smart R:R passes
      - Mode C (108883): fires when Mode B passes AND direction aligns with EMA50
    """
    digits = PAIR_DIGITS.get(pair, 5 if "JPY" not in pair and "XAU" not in pair else 3)
    default_spread = 0.35 if "XAU" in pair else (0.02 if "JPY" in pair else 0.0002)
    spread = SPREAD_USD.get(pair, default_spread)
    lot = LOT_SIZE.get(pair, 0.01)

    up = max(0.0, pred_high_3 - last_close)
    dn = max(0.0, last_close - pred_low_3)
    conf = max(up, dn) / (up + dn + 1e-9)
    min_move = max(spread * 2.5, atr * 0.9)

    direction = "flat"
    tp_dist = 0.0
    sl_dist = 0.0

    if up > dn and up >= min_move and conf >= 0.65:
        cand_tp = min(up, atr * 2.2)
        cand_sl = max(spread * 2.5, atr * 0.85)
        if cand_tp >= cand_sl * 1.25:
            direction, tp_dist, sl_dist = "long", cand_tp, cand_sl
    elif dn > up and dn >= min_move and conf >= 0.65:
        cand_tp = min(dn, atr * 2.2)
        cand_sl = max(spread * 2.5, atr * 0.85)
        if cand_tp >= cand_sl * 1.25:
            direction, tp_dist, sl_dist = "short", cand_tp, cand_sl

    def _make_sig(sig_dir, magic, comment):
        if sig_dir == "long":
            tp = round(last_close + tp_dist, digits)
            sl = round(last_close - sl_dist, digits)
            mv = round(tp_dist, digits)
            sz = lot
            sf = True
        elif sig_dir == "short":
            tp = round(last_close - tp_dist, digits)
            sl = round(last_close + sl_dist, digits)
            mv = round(tp_dist, digits)
            sz = lot
            sf = True
        else:
            tp = None
            sl = None
            mv = 0.0
            sz = 0.0
            sf = False
        return {
            "pair":           pair,
            "timestamp":      str(timestamp),
            "direction":      sig_dir,
            "confidence":     round(conf, 4) if sig_dir != "flat" else 0.0,
            "predicted_high": round(pred_high_3, digits),
            "predicted_low":  round(pred_low_3, digits),
            "target_price":   tp,
            "stop_price":     sl,
            "predicted_move": mv,
            "sl_distance":    round(sl_dist, digits) if sig_dir != "flat" else 0.0,
            "lot_size":       sz,
            "spread_filter":  sf,
            "atr":            round(atr, digits),
            "magic":          magic,
            "comment":        comment,
        }

    # Mode B: Smart R:R (no EMA50 trend restriction)
    sig_b = _make_sig(direction, 108882, "Kronos-ModeB")

    # Mode C: Smart R:R + EMA50 Trend Alignment
    dir_c = direction
    if dir_c == "long" and last_close < ema50:
        dir_c = "flat"
    elif dir_c == "short" and last_close > ema50:
        dir_c = "flat"
    sig_c = _make_sig(dir_c, 108883, "Kronos-ModeC")

    return {"mode_b": sig_b, "mode_c": sig_c}
