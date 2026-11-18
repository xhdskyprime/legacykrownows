//+------------------------------------------------------------------+
//| KronosEA.mq5                                                     |
//| Kronos Trading System — Pure AI v3.1 (Stepped Trailing Edition)  |
//| Pure Kronos AI Market Execution (No Grid Limit Orders)           |
//| Isolated Magic 108888 (Manual Trades Untouched)                  |
//| Multi-Stage Stepped Trailing Stop (BEP -> Cuan 1 -> Cuan 2)      |
//+------------------------------------------------------------------+
#property copyright "Kronos Trading System"
#property link      "https://github.com/xhdskyprime/legacykrownows"
#property version   "3.10"
#property strict

#include <Trade\Trade.mqh>

//── Input parameters ──────────────────────────────────────────────
input string SignalFile            = "signal.json";     // File sinyal dari Python AI
input string AckFile               = "signal_ack.json"; // File konfirmasi balasan EA
input int    MagicNumber           = 108888;            // Magic Number terisolasi khusus bot
input int    MaxPositionsPerPair   = 2;                 // Maksimal posisi bot per instrumen (Golden Setup: 2)
input bool   EnableSteppedTrailing = true;              // Aktifkan Trailing Bertingkat (BEP -> Tangga Profit)

//── Trade object ──────────────────────────────────────────────────
CTrade trade;

//+------------------------------------------------------------------+
//| Hapus pending orders milik bot (Magic 108888) jika tersisa       |
//+------------------------------------------------------------------+
void DeleteAllBotPendingOrders()
{
    int deleted = 0;
    for (int i = OrdersTotal() - 1; i >= 0; i--)
    {
        ulong ticket = OrderGetTicket(i);
        if (ticket == 0) continue;
        if (OrderGetInteger(ORDER_MAGIC) == MagicNumber)
        {
            if (trade.OrderDelete(ticket))
                deleted++;
        }
    }
    if (deleted > 0)
        Print("Kronos Pure AI: Membersihkan ", deleted, " pending order grid lama milik bot.");
}

//+------------------------------------------------------------------+
//| EA initialisation                                                |
//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetExpertMagicNumber(MagicNumber);
    trade.SetDeviationInPoints(50);
    trade.SetTypeFilling(ORDER_FILLING_IOC);

    // Bersihkan sisa pending order grid lama milik bot saja (manual 100% aman)
    DeleteAllBotPendingOrders();

    EventSetTimer(3); // Cek sinyal & kelola trailing bertingkat setiap 3 detik
    Print("================================================================");
    Print("Kronos Pure AI v3.1 (Stepped Trailing Edition — No Grid) Started");
    Print("Magic Number: ", MagicNumber, " | Max Positions/Pair: ", MaxPositionsPerPair);
    Print("Trailing Bertingkat: ", (EnableSteppedTrailing ? "AKTIF (0.5 ATR BEP -> Tangga Profit)" : "MATI"));
    Print("Isolasi Manual: AKTIF (Hanya mengelola Magic ", MagicNumber, ")");
    Print("================================================================");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| EA cleanup                                                       |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
    Print("Kronos Pure AI v3.1 stopped.");
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
//| Hitung posisi milik robot ini (Magic 108888)                     |
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
//| Stepped Trailing Stop Manager (Trailing Bertingkat):             |
//| Tangga 1: Profit >= 0.5 ATR  -> Kunci BEP (+10 point) Zero-Risk  |
//| Tangga 2: Profit >= 1.0 ATR  -> Kunci Cuan 1 (+0.4 ATR)          |
//| Tangga 3: Profit >= 1.8 ATR  -> Kunci Cuan 2 (+1.0 ATR)          |
//| Tangga 4: Profit >= 2.5 ATR  -> Trail Dinamis (Price - 0.8 ATR)  |
//+------------------------------------------------------------------+
void ManageSteppedTrailingStop()
{
    if (!EnableSteppedTrailing) return;

    for (int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if (ticket == 0) continue;
        if (PositionGetInteger(POSITION_MAGIC) != MagicNumber) continue;

        string sym        = PositionGetString(POSITION_SYMBOL);
        long   pos_type   = PositionGetInteger(POSITION_TYPE);
        double open_price = PositionGetDouble(POSITION_PRICE_OPEN);
        double curr_sl    = PositionGetDouble(POSITION_SL);
        double curr_tp    = PositionGetDouble(POSITION_TP);
        int    digits     = (int)SymbolInfoInteger(sym, SYMBOL_DIGITS);
        double point      = SymbolInfoDouble(sym, SYMBOL_POINT);
        long   stop_level = SymbolInfoInteger(sym, SYMBOL_TRADE_STOPS_LEVEL);

        if (point <= 0) continue;
        double min_stop_dist = MathMax((double)stop_level, 10.0) * point;

        MqlTick tick;
        if (!SymbolInfoTick(sym, tick) || tick.bid <= 0 || tick.ask <= 0) continue;
        double bid = tick.bid;
        double ask = tick.ask;

        // Dapatkan nilai ATR H1 live
        double atr_val = 0.0;
        int atr_handle = iATR(sym, PERIOD_H1, 14);
        if (atr_handle != INVALID_HANDLE)
        {
            double atr_buf[1];
            if (CopyBuffer(atr_handle, 0, 0, 1, atr_buf) > 0)
            {
                atr_val = atr_buf[0];
            }
            IndicatorRelease(atr_handle);
        }
        if (atr_val <= 0) atr_val = 150 * point;

        if (pos_type == POSITION_TYPE_BUY)
        {
            double profit_dist = bid - open_price;
            double target_sl   = 0.0;

            if (profit_dist >= 2.5 * atr_val)
                target_sl = bid - (0.8 * atr_val);
            else if (profit_dist >= 1.8 * atr_val)
                target_sl = open_price + (1.0 * atr_val);
            else if (profit_dist >= 1.0 * atr_val)
                target_sl = open_price + (0.4 * atr_val);
            else if (profit_dist >= 0.5 * atr_val)
                target_sl = open_price + (10 * point);

            if (target_sl > 0)
            {
                target_sl = NormalizeDouble(target_sl, digits);
                if (target_sl > (curr_sl + 3 * point) && target_sl < (bid - min_stop_dist))
                {
                    if (trade.PositionModify(ticket, target_sl, curr_tp))
                    {
                        Print("Kronos Pure AI: TANGGA TRAILING BUY ", sym, " #", ticket,
                              " dinaikkan --> ", target_sl, " (Profit: +", DoubleToString(profit_dist / point, 0), " pts)");
                    }
                }
            }
        }
        else if (pos_type == POSITION_TYPE_SELL)
        {
            double profit_dist = open_price - ask;
            double target_sl   = 0.0;

            if (profit_dist >= 2.5 * atr_val)
                target_sl = ask + (0.8 * atr_val);
            else if (profit_dist >= 1.8 * atr_val)
                target_sl = open_price - (1.0 * atr_val);
            else if (profit_dist >= 1.0 * atr_val)
                target_sl = open_price - (0.4 * atr_val);
            else if (profit_dist >= 0.5 * atr_val)
                target_sl = open_price - (10 * point);

            if (target_sl > 0)
            {
                target_sl = NormalizeDouble(target_sl, digits);
                if ((curr_sl == 0 || target_sl < (curr_sl - 3 * point)) && target_sl > (ask + min_stop_dist))
                {
                    if (trade.PositionModify(ticket, target_sl, curr_tp))
                    {
                        Print("Kronos Pure AI: TANGGA TRAILING SELL ", sym, " #", ticket,
                              " dimajukan --> ", target_sl, " (Profit: +", DoubleToString(profit_dist / point, 0), " pts)");
                    }
                }
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Main logic — Eksekusi Pure Kronos AI (Tanpa Grid Limit)          |
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

    if (direction == "" || pair == "") return;

    Print("Kronos Pure AI: Sinyal diterima | pair=", pair, " dir=", direction,
          " lot=", lot_size, " TP=", target, " SL=", stop);

    int bot_buys      = CountBotPositions(pair, POSITION_TYPE_BUY);
    int bot_sells     = CountBotPositions(pair, POSITION_TYPE_SELL);
    int total_bot_pos = bot_buys + bot_sells;

    long ticket       = 0;
    bool order_placed = false;

    // Pastikan simbol aktif di Market Watch
    SymbolSelect(pair, true);

    int digits   = (int)SymbolInfoInteger(pair, SYMBOL_DIGITS);
    double point = SymbolInfoDouble(pair, SYMBOL_POINT);
    if (point <= 0) point = (digits == 5) ? 0.00001 : ((digits == 3) ? 0.001 : 0.01);

    MqlTick tick;
    if (!SymbolInfoTick(pair, tick) || tick.bid <= 0 || tick.ask <= 0)
    {
        Print("Kronos Pure AI: Menunggu harga live untuk ", pair, ". Melewati sinyal ini.");
        FileDelete(SignalFile, FILE_COMMON);
        return;
    }

    double bid = tick.bid;
    double ask = tick.ask;

    if (direction == "flat")
    {
        order_placed = true;
    }
    // Anti-Hedging khusus posisi bot (tidak mempedulikan trade manual)
    else if ((direction == "long" && bot_sells > 0) || (direction == "short" && bot_buys > 0))
    {
        Print("Kronos Pure AI: Melewati ", direction, " ", pair, " karena ada posisi lawan arah milik bot.");
        order_placed = true;
    }
    // Maksimal posisi per pair khusus bot
    else if (total_bot_pos >= MaxPositionsPerPair)
    {
        Print("Kronos Pure AI: Maksimal ", MaxPositionsPerPair, " posisi bot untuk ", pair, " sudah aktif. Melewati.");
        order_placed = true;
    }
    else if (direction == "long")
    {
        if (bid > 0 && stop >= bid && stop > 0)
            stop = NormalizeDouble(bid - 150 * point, digits);

        if (trade.Buy(lot_size, pair, 0, stop, target, "Kronos-AI"))
        {
            ticket = (long)trade.ResultOrder();
            order_placed = true;
            Print("Kronos Pure AI: BUY berhasil dibuka (Layer #", total_bot_pos + 1, ") di ", ask, ". Ticket=", ticket);
        }
        else
        {
            Print("Kronos Pure AI: Gagal BUY ", pair, "! Error: ", trade.ResultRetcode(), " - ", trade.ResultRetcodeDescription());
        }
    }
    else if (direction == "short")
    {
        if (ask > 0 && stop <= ask && stop > 0)
            stop = NormalizeDouble(ask + 150 * point, digits);

        if (trade.Sell(lot_size, pair, 0, stop, target, "Kronos-AI"))
        {
            ticket = (long)trade.ResultOrder();
            order_placed = true;
            Print("Kronos Pure AI: SELL berhasil dibuka (Layer #", total_bot_pos + 1, ") di ", bid, ". Ticket=", ticket);
        }
        else
        {
            Print("Kronos Pure AI: Gagal SELL ", pair, "! Error: ", trade.ResultRetcode(), " - ", trade.ResultRetcodeDescription());
        }
    }

    if (order_placed)
    {
        string ack = "{\n  \"status\": \"executed\",\n  \"order_ticket\": "
                     + IntegerToString(ticket) + "\n}\n";
        WriteFile(AckFile, ack);
    }
    else
    {
        string ack = "{\n  \"status\": \"failed\",\n  \"error\": "
                     + IntegerToString(trade.ResultRetcode()) + "\n}\n";
        WriteFile(AckFile, ack);
    }

    FileDelete(SignalFile, FILE_COMMON);
}

//+------------------------------------------------------------------+
//| Timer event handler                                              |
//+------------------------------------------------------------------+
void OnTimer()
{
    ProcessSignalFile();
    ManageSteppedTrailingStop();
}
//+------------------------------------------------------------------+
