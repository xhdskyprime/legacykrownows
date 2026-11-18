# compare_ab.py
# Live A/B Scoreboard: Mode B (Magic 108882) vs Mode C (Magic 108883)
import datetime
import MetaTrader5 as mt5

MAGIC_B = 108882
MAGIC_C = 108883


def main():
    mt5.initialize()
    now = datetime.datetime.now()
    # Look back up to 30 days (captures everything since Dual-Mode A/B launched)
    start = now - datetime.timedelta(days=30)

    deals = mt5.history_deals_get(start, now) or []
    positions = mt5.positions_get() or []

    print("=" * 82)
    print(f"KRONOS DUAL-MODE LIVE A/B SCOREBOARD ({now.strftime('%Y-%m-%d %H:%M:%S WIB')})")
    print("=" * 82)

    for label, magic in [("MODE B (Smart R:R p=3)", MAGIC_B), ("MODE C (Smart R:R p=3 + EMA50)", MAGIC_C)]:
        closed = [d for d in deals if d.magic == magic and d.entry == 1]
        opened = [p for p in positions if p.magic == magic]

        realized = sum(d.profit + d.swap + d.commission for d in closed)
        floating = sum(p.profit + p.swap for p in opened)
        wins = [d for d in closed if (d.profit + d.swap + d.commission) > 0]
        losses = [d for d in closed if (d.profit + d.swap + d.commission) <= 0]
        wr = (len(wins) / len(closed) * 100) if closed else 0.0
        avg_w = (sum(d.profit + d.swap + d.commission for d in wins) / len(wins)) if wins else 0.0
        avg_l = (sum(d.profit + d.swap + d.commission for d in losses) / len(losses)) if losses else 0.0
        xau_pnl = sum(d.profit + d.swap + d.commission for d in closed if d.symbol == "XAUUSDc")

        print(f"\n[{label} | Magic {magic}]")
        print(f"  Closed Trades : {len(closed)} (Win: {len(wins)} | Loss: {len(losses)} | WR: {wr:.1f}%)")
        print(f"  Realized PnL  : {realized:+.2f} USC (${realized/100:+.2f} USD) | Gold Only: {xau_pnl:+.2f} USC")
        print(f"  Avg Win / Loss: {avg_w:+.2f} USC / {avg_l:+.2f} USC")
        print(f"  Open Positions: {len(opened)} (Floating: {floating:+.2f} USC)")
        print(f"  TOTAL NET     : {realized + floating:+.2f} USC")

    acc = mt5.account_info()
    print("\n" + "-" * 82)
    print(f"Account Balance: {acc.balance:,.2f} USC | Equity: {acc.equity:,.2f} USC | Margin Level: {acc.margin_level:,.1f}%")
    mt5.shutdown()


if __name__ == "__main__":
    main()
