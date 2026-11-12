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

    lot = LOT_SIZE.get(pair, 0.02 if "XAU" in pair else 0.05)

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
