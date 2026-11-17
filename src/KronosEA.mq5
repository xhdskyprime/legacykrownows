//+------------------------------------------------------------------+
//| KronosEA.mq5                                                     |
//| Kronos Trading System — Hybrid AI-Grid v3.0                      |
//| Combines Kronos Deep Learning Directional Forecast with           |
//| ATR-Adaptive Pullback Grid & Basket Profit Management            |
//+------------------------------------------------------------------+
#property copyright "Kronos Trading System"
#property link      "https://github.com/xhdskyprime/legacykrownows"
#property version   "3.00"
#property strict

#include <Trade\Trade.mqh>

//── Input parameters ──────────────────────────────────────────────
input string SignalFile             = "signal.json";     // File sinyal dari Python AI
input string AckFile                = "signal_ack.json"; // File konfirmasi balasan EA
input int    MagicNumber            = 108888;            // Magic Number terisolasi bot
input int    MaxGridLayers          = 2;                 // Maksimal layer grid per instrumen (Golden Setup: 2)
input double ATRMultiplierStep      = 0.75;              // Pengali ATR untuk jarak jaring pullback
input bool   EnableBasketClose      = true;              // Tutup serentak seluruh keranjang saat profit tercapai
input bool   EnableTrailingStop     = true;              // Aktifkan Trailing Stop & BEP pada posisi single
input double BasketProfitTargetUSC  = 3.0;               // Target profit keranjang gabungan (dalam sen/USC)

//── Trade object ──────────────────────────────────────────────────
CTrade trade;

//+------------------------------------------------------------------+
//| EA initialisation                                                |
//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(50);
    trade.SetTypeFilling(ORDER_FILLING_IOC);

    EventSetTimer(3); // Cek sinyal & kelola keranjang/trailing setiap 3 detik
    Print("================================================================");
    Print("Kronos Hybrid AI-Grid v3.0 started | Magic: ", MagicNumber);
    Print("Max Grid Layers: ", MaxGridLayers, " | ATR Step Multiplier: ", ATRMultiplierStep);
    Print("================================================================");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| EA cleanup                                                       |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
    Print("Kronos Hybrid AI-Grid v3.0 stopped.");
}

//+------------------------------------------------------------------+
//| Helper extract JSON fields                                       |
//+------------------------------------------------------------------+
string ExtractField(const string json, const string key)
{
    string pattern = "\"" + key + "\": ";
    int pos = StringFind(json, pattern, 0);
    if (pos < 0)
    {
        pattern = "\"" + key + "\":";
        pos = StringFind(json, pattern, 0);
        if (pos < 0) return "";
    }

    int val_start = pos + StringLen(pattern);
    if (StringSubstr(json, val_start, 1) == "\"")
    {
        int val_end = StringFind(json, "\"", val_start + 1);
        if (val_end < 0) return "";
        return StringSubstr(json, val_start + 1, val_end - val_start - 1);
    }

    int val_end = val_start;
    int json_len = StringLen(json);
    while (val_end < json_len)
    {
        string ch = StringSubstr(json, val_end, 1);
        if (ch == "," || ch == "}" || ch == "\r" || ch == "\n")
            break;
        val_end++;
    }

    string result = StringSubstr(json, val_start, val_end - val_start);
    StringTrimRight(result);
    StringTrimLeft(result);
    return result;
}

//+------------------------------------------------------------------+
//| File I/O helpers                                                 |
//+------------------------------------------------------------------+
string ReadFile(const string filename)
{
    int fh = FileOpen(filename, FILE_READ | FILE_BIN | FILE_COMMON);
    if (fh == INVALID_HANDLE) return "";
    ulong file_size = FileSize(fh);
    if (file_size == 0) { FileClose(fh); return ""; }

    uchar buf[];
    ArrayResize(buf, (int)file_size);
    FileReadArray(fh, buf, 0, (int)file_size);
    FileClose(fh);
    return CharArrayToString(buf, 0, (int)file_size);
}

bool WriteFile(const string filename, const string text)
{
    int fh = FileOpen(filename, FILE_WRITE | FILE_TXT | FILE_COMMON);
    if (fh == INVALID_HANDLE) return false;
    FileWriteString(fh, text);
    FileClose(fh);
    return true;
}

//+------------------------------------------------------------------+
//| Hitung posisi milik robot ini (Magic 108888)                      |
//+------------------------------------------------------------------+
int CountBotPositions(const string sym, const ENUM_POSITION_TYPE pos_type)
{
    int count = 0;
    for (int i = 0; i < PositionsTotal(); i++)
    {
        ulong ticket = PositionGetTicket(i);
        if (ticket == 0) continue;
        if (PositionGetString(POSITION_SYMBOL) == sym &&
            PositionGetInteger(POSITION_MAGIC) == MagicNumber &&
            PositionGetInteger(POSITION_TYPE) == pos_type)
        {
            count++;
        }
    }
    return count;
}

//+------------------------------------------------------------------+
//| Hitung pending limit orders milik robot ini                      |
//+------------------------------------------------------------------+
int CountBotPendingOrders(const string sym, const ENUM_ORDER_TYPE order_type)
{
    int count = 0;
    for (int i = 0; i < OrdersTotal(); i++)
    {
        ulong ticket = OrderGetTicket(i);
        if (ticket == 0) continue;
        if (OrderGetString(ORDER_SYMBOL) == sym &&
            OrderGetInteger(ORDER_MAGIC) == MagicNumber &&
            OrderGetInteger(ORDER_TYPE) == order_type)
        {
            count++;
        }
    }
    return count;
}

//+------------------------------------------------------------------+
//| Hapus pending orders kadaluarsa untuk symbol ini                 |
//+------------------------------------------------------------------+
void DeleteBotPendingOrders(const string sym)
{
    for (int i = OrdersTotal() - 1; i >= 0; i--)
    {
        ulong ticket = OrderGetTicket(i);
        if (ticket == 0) continue;
        if (OrderGetString(ORDER_SYMBOL) == sym && OrderGetInteger(ORDER_MAGIC) == MagicNumber)
        {
            trade.OrderDelete(ticket);
        }
    }
}

//+------------------------------------------------------------------+
//| Basket Take Profit Manager:                                      |
//| Jika total profit keranjang >= BasketProfitTarget -> Tutup Semua |
//+------------------------------------------------------------------+
void ManageBasketProfit()
{
    if (!EnableBasketClose) return;

    // Kumpulkan symbol aktif milik bot
    string active_syms[];
    int sym_count = 0;

    for (int i = 0; i < PositionsTotal(); i++)
    {
        ulong ticket = PositionGetTicket(i);
        if (ticket == 0) continue;
        if (PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;

        string sym = PositionGetString(POSITION_SYMBOL);
        bool found = false;
        for (int s = 0; s < sym_count; s++)
        {
            if (active_syms[s] == sym) { found = true; break; }
        }
        if (!found)
        {
            ArrayResize(active_syms, sym_count + 1);
            active_syms[sym_count] = sym;
            sym_count++;
        }
    }

    // Evaluasi profit per symbol keranjang
    for (int s = 0; s < sym_count; s++)
    {
        string sym = active_syms[s];
        double total_profit = 0.0;
        int pos_count = 0;

        for (int i = 0; i < PositionsTotal(); i++)
        {
            ulong ticket = PositionGetTicket(i);
            if (ticket == 0) continue;
            if (PositionGetString(POSITION_SYMBOL) == sym && PositionGetInteger(POSITION_MAGIC) == MagicNumber)
            {
                total_profit += (PositionGetDouble(POSITION_PROFIT) + PositionGetDouble(POSITION_SWAP));
                pos_count++;
            }
        }

        // Jika keranjang berisi lebih dari 1 posisi dan profit sudah capai target
        if (pos_count >= 2 && total_profit >= BasketProfitTargetUSC)
        {
            Print("Kronos Hybrid: BASKET PROFIT TERCAPAI pada ", sym, "! Profit=", total_profit, " USC (", pos_count, " posisi). Menutup keranjang...");
            DeleteBotPendingOrders(sym);

            for (int i = PositionsTotal() - 1; i >= 0; i--)
            {
                ulong ticket = PositionGetTicket(i);
                if (ticket == 0) continue;
                if (PositionGetString(POSITION_SYMBOL) == sym && PositionGetInteger(POSITION_MAGIC) == MagicNumber)
                {
                    trade.PositionClose(ticket);
                }
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Trailing Stop Manager untuk Single Position                       |
//+------------------------------------------------------------------+
void ManageSingleTrailingStop()
{
    if (!EnableTrailingStop) return;

    for (int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if (ticket == 0) continue;
        if (PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;

        string sym = PositionGetString(POSITION_SYMBOL);

        // Jika ada 2 layer terbuka, biarkan Basket Manager yang menangani
        int buy_pos = CountBotPositions(sym, POSITION_TYPE_BUY);
        int sell_pos = CountBotPositions(sym, POSITION_TYPE_SELL);
        if ((buy_pos + sell_pos) > 1) continue;

        long   pos_type   = PositionGetInteger(POSITION_TYPE);
        double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
        double curr_sl    = PositionGetDouble(POSITION_SL);
        double curr_tp    = PositionGetDouble(POSITION_TP);
        int    digits     = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
        double point      = SymbolInfoDouble(sym, SYMBOL_POINT);
        double bid        = SymbolInfoDouble(sym, SYMBOL_BID);
        double ask        = SymbolInfoDouble(sym, SYMBOL_ASK);

        if (pos_type == POSITION_TYPE_BUY)
        {
            double profit_dist = bid - open_price;
            double initial_risk = (curr_sl > 0) ? (open_price - curr_sl) : (150 * point);
            if (initial_risk <= 0) initial_risk = 150 * point;

            if (profit_dist >= initial_risk)
            {
                double trail_step = initial_risk * 0.75;
                double new_sl = NormalizeDouble(bid - trail_step, digits);
                double be_sl  = NormalizeDouble(open_price + (10 * point), digits);

                if (new_sl < be_sl) new_sl = be_sl;

                if (new_sl > (curr_sl + 3 * point))
                {
                    trade.PositionModify(ticket, new_sl, curr_tp);
                    Print("Kronos Hybrid: Trailing SL BUY ", sym, " #", ticket, " --> ", new_sl);
                }
            }
        }
        else if (pos_type == POSITION_TYPE_SELL)
        {
            double profit_dist = open_price - ask;
            double initial_risk = (curr_sl > 0) ? (curr_sl - open_price) : (150 * point);
            if (initial_risk <= 0) initial_risk = 150 * point;

            if (profit_dist >= initial_risk)
            {
                double trail_step = initial_risk * 0.75;
                double new_sl = NormalizeDouble(ask + trail_step, digits);
                double be_sl  = NormalizeDouble(open_price - (10 * point), digits);

                if (new_sl > be_sl) new_sl = be_sl;

                if (curr_sl == 0 || new_sl < (curr_sl - 3 * point))
                {
                    trade.PositionModify(ticket, new_sl, curr_tp);
                    Print("Kronos Hybrid: Trailing SL SELL ", sym, " #", ticket, " --> ", new_sl);
                }
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Main logic — Eksekusi Hybrid AI-Grid                             |
//+------------------------------------------------------------------+
void ProcessSignalFile()
{
    string content = ReadFile(SignalFile);
    if (content == "") return;

    string direction = ExtractField(content, "direction");
    string pair      = ExtractField(content, "pair");
    double lot_size  = StringToDouble(ExtractField(content, "lot_size"));
    double target    = StringToDouble(ExtractField(content, "target_price"));
    double stop      = StringToDouble(ExtractField(content, "stop_price"));
    double atr       = StringToDouble(ExtractField(content, "atr"));

    if (direction == "" || pair == "") return;

    Print("Kronos Hybrid: Sinyal diterima | pair=", pair, " dir=", direction,
          " lot=", lot_size, " ATR=", atr, " TP=", target, " SL=", stop);

    int bot_buys  = CountBotPositions(pair, POSITION_TYPE_BUY);
    int bot_sells = CountBotPositions(pair, POSITION_TYPE_SELL);
    int total_bot_pos = bot_buys + bot_sells;

    long ticket = 0;
    bool order_placed = false;

    int digits = (int)SymbolInfoInteger(pair, SYMBOL_DIGITS);
    double point = SymbolInfoDouble(pair, SYMBOL_POINT);
    double bid = SymbolInfoDouble(pair, SYMBOL_BID);
    double ask = SymbolInfoDouble(pair, SYMBOL_ASK);

    // Hitung step grid adaptif berdasarkan ATR
    double grid_step = (atr > 0) ? (atr * ATRMultiplierStep) : (150 * point);

    if (direction == "flat")
    {
        order_placed = true;
    }
    // Anti-Hedging: jika ada posisi lawan arah yang terbuka, lewati
    else if ((direction == "long" && bot_sells > 0) || (direction == "short" && bot_buys > 0))
    {
        Print("Kronos Hybrid: Melewati ", direction, " ", pair, " karena masih ada posisi lawan arah milik bot.");
        order_placed = true;
    }
    // Maksimal posisi per pair
    else if (total_bot_pos >= MaxGridLayers)
    {
        Print("Kronos Hybrid: Maksimal ", MaxGridLayers, " layer untuk ", pair, " sudah aktif. Melewati.");
        order_placed = true;
    }
    else if (direction == "long")
    {
        // ── BULLISH GRID ──
        if (stop >= bid && stop > 0)
        {
            stop = NormalizeDouble(bid - 150 * point, digits);
        }

        // Layer #1: Masuk Market jika belum ada posisi
        if (total_bot_pos == 0)
        {
            if (trade.Buy(lot_size, pair, 0, stop, target, "Kronos-L1"))
            {
                ticket = trade.ResultOrder();
                order_placed = true;
                Print("Kronos Hybrid: BUY Layer #1 berhasil dibuka di ", ask, ". Ticket=", ticket);

                // Pasang Jaring Diskon Layer #2 (Buy Limit pada harga pullback)
                double limit_price = NormalizeDouble(ask - grid_step, digits);
                double limit_tp    = NormalizeDouble(ask, digits); // TP di harga open Layer #1
                double limit_sl    = NormalizeDouble(limit_price - (grid_step * 1.5), digits);

                DeleteBotPendingOrders(pair);
                if (trade.BuyLimit(lot_size, limit_price, pair, limit_sl, limit_tp, ORDER_TIME_GTC, 0, "Kronos-L2-Grid"))
                {
                    Print("Kronos Hybrid: Jaring BUY LIMIT Layer #2 berhasil dipasang di harga diskon: ", limit_price);
                }
            }
        }
        // Jika sudah ada 1 posisi dan sinyal tetap bullish, biarkan jaring limit bekerja
        else
        {
            Print("Kronos Hybrid: Layer #1 sedang aktif di ", pair, ". Menunggu pullback menabrak jaring diskon.");
            order_placed = true;
        }
    }
    else if (direction == "short")
    {
        // ── BEARISH GRID ──
        if (stop <= ask && stop > 0)
        {
            stop = NormalizeDouble(ask + 150 * point, digits);
        }

        // Layer #1: Masuk Market jika belum ada posisi
        if (total_bot_pos == 0)
        {
            if (trade.Sell(lot_size, pair, 0, stop, target, "Kronos-L1"))
            {
                ticket = trade.ResultOrder();
                order_placed = true;
                Print("Kronos Hybrid: SELL Layer #1 berhasil dibuka di ", bid, ". Ticket=", ticket);

                // Pasang Jaring Diskon Layer #2 (Sell Limit pada harga rally/koreksi atas)
                double limit_price = NormalizeDouble(bid + grid_step, digits);
                double limit_tp    = NormalizeDouble(bid, digits); // TP di harga open Layer #1
                double limit_sl    = NormalizeDouble(limit_price + (grid_step * 1.5), digits);

                DeleteBotPendingOrders(pair);
                if (trade.SellLimit(lot_size, limit_price, pair, limit_sl, limit_tp, ORDER_TIME_GTC, 0, "Kronos-L2-Grid"))
                {
                    Print("Kronos Hybrid: Jaring SELL LIMIT Layer #2 berhasil dipasang di harga rally: ", limit_price);
                }
            }
        }
        else
        {
            Print("Kronos Hybrid: Layer #1 sedang aktif di ", pair, ". Menunggu rally menabrak jaring diskon.");
            order_placed = true;
        }
    }

    if (!order_placed) return;

    // Tulis konfirmasi ke Python
    string ack = "{\n  \"status\": \"executed\",\n  \"order_ticket\": "
                 + IntegerToString(ticket) + "\n}\n";
    WriteFile(AckFile, ack);

    // Hapus file sinyal agar EA siap menerima sinyal berikutnya
    FileDelete(SignalFile, FILE_COMMON);
}

//+------------------------------------------------------------------+
//| Timer event handler                                              |
//+------------------------------------------------------------------+
void OnTimer()
{
    ProcessSignalFile();
    ManageBasketProfit();
    ManageSingleTrailingStop();
}
