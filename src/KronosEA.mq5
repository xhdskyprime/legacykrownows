//+------------------------------------------------------------------+
//| KronosEA.mq5                                                     |
//| Kronos Trading System — Dual-Mode A/B v3.2 (Stepped Trailing)    |
//| Simultaneous Live Comparison: Mode B (108882) vs Mode C (108883) |
//| Isolated Magic Numbers (Manual Trades Magic 0 100% Untouched)    |
//| Multi-Stage Stepped Trailing Stop (BEP -> Cuan 1 -> Cuan 2)      |
//+------------------------------------------------------------------+
#property copyright "Kronos Trading System"
#property link      "https://github.com/xhdskyprime/legacykrownows"
#property version   "3.20"
#property strict

#include <Trade\Trade.mqh>

//── Input parameters ──────────────────────────────────────────────
input string SignalFile            = "signal.json";     // File sinyal dari Python AI
input string AckFile               = "signal_ack.json"; // File konfirmasi balasan EA
input int    MagicModeB            = 108882;            // Magic Number khusus Mode B (Smart R:R p=3)
input int    MagicModeC            = 108883;            // Magic Number khusus Mode C (Smart R:R p=3 + EMA50)
input int    MagicLegacy           = 108888;            // Magic Number lama (tetap dikawal Stepped Trailing)
input int    MaxPositionsPerMode   = 2;                 // Maksimal posisi per mode per pair
input bool   EnableSteppedTrailing = true;              // Aktifkan Trailing Bertingkat (0.5 ATR BEP -> Tangga)

//── Trade object ──────────────────────────────────────────────────
CTrade trade;

//+------------------------------------------------------------------+
//| Cek apakah Magic Number milik sistem Kronos                      |
//+------------------------------------------------------------------+
bool IsBotMagic(const long magic)
{
    return (magic == MagicModeB || magic == MagicModeC || magic == MagicLegacy);
}

//+------------------------------------------------------------------+
//| EA initialisation                                                |
//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetDeviationInPoints(50);
    trade.SetTypeFilling(ORDER_FILLING_IOC);

    EventSetTimer(2); // Cek sinyal cepat & kelola trailing bertingkat setiap 2 detik
    Print("================================================================");
    Print("Kronos Dual-Mode A/B v3.2 (Mode B vs Mode C) Started");
    Print("Mode B Magic: ", MagicModeB, " | Mode C Magic: ", MagicModeC, " | Legacy: ", MagicLegacy);
    Print("Max Positions/Pair/Mode: ", MaxPositionsPerMode);
    Print("Trailing Bertingkat: ", (EnableSteppedTrailing ? "AKTIF (0.5 ATR BEP -> Tangga Profit)" : "MATI"));
    Print("Isolasi Manual: AKTIF (Order manual Magic 0 100% tidak disentuh)");
    Print("================================================================");
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| EA cleanup                                                       |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
    Print("Kronos Dual-Mode A/B v3.2 stopped.");
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
//| Hitung posisi khusus untuk (symbol, magic, pos_type)             |
//+------------------------------------------------------------------+
int CountModePositions(const string sym, const long magic, const ENUM_POSITION_TYPE pos_type)
{
    int count = 0;
    for (int i = 0; i < PositionsTotal(); i++)
    {
        ulong ticket = PositionGetTicket(i);
        if (ticket == 0) continue;
        if (PositionGetString(POSITION_SYMBOL) == sym &&
            PositionGetInteger(POSITION_MAGIC) == magic &&
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

        long pos_magic = PositionGetInteger(POSITION_MAGIC);
        if (!IsBotMagic(pos_magic)) continue;

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

        string mode_tag = (pos_magic == MagicModeB) ? "[ModeB]" : ((pos_magic == MagicModeC) ? "[ModeC]" : "[Legacy]");

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
                        Print("Kronos ", mode_tag, ": TANGGA TRAILING BUY ", sym, " #", ticket,
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
                        Print("Kronos ", mode_tag, ": TANGGA TRAILING SELL ", sym, " #", ticket,
                              " dimajukan --> ", target_sl, " (Profit: +", DoubleToString(profit_dist / point, 0), " pts)");
                    }
                }
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Main logic — Eksekusi Dual-Mode A/B (Mode B 108882 / C 108883)   |
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
    string magic_str = ExtractField(content, "magic");
    string comment   = ExtractField(content, "comment");

    if (direction == "" || pair == "") return;

    long sig_magic = (magic_str != "") ? StringToInteger(magic_str) : MagicLegacy;
    if (!IsBotMagic(sig_magic)) sig_magic = MagicLegacy;
    if (comment == "") comment = "Kronos-AI";

    trade.SetExpertMagicNumber(sig_magic);

    Print("Kronos [", comment, "|", sig_magic, "]: Sinyal | pair=", pair, " dir=", direction,
          " lot=", lot_size, " TP=", target, " SL=", stop);

    int mode_buys      = CountModePositions(pair, sig_magic, POSITION_TYPE_BUY);
    int mode_sells     = CountModePositions(pair, sig_magic, POSITION_TYPE_SELL);
    int total_mode_pos = mode_buys + mode_sells;

    long ticket       = 0;
    bool order_placed = false;

    SymbolSelect(pair, true);

    int digits   = (int)SymbolInfoInteger(pair, SYMBOL_DIGITS);
    double point = SymbolInfoDouble(pair, SYMBOL_POINT);
    if (point <= 0) point = (digits == 5) ? 0.00001 : ((digits == 3) ? 0.001 : 0.01);

    MqlTick tick;
    if (!SymbolInfoTick(pair, tick) || tick.bid <= 0 || tick.ask <= 0)
    {
        Print("Kronos [", comment, "]: Menunggu harga live untuk ", pair, ". Melewati.");
        FileDelete(SignalFile, FILE_COMMON);
        return;
    }

    double bid = tick.bid;
    double ask = tick.ask;

    if (direction == "flat")
    {
        order_placed = true;
    }
    // Anti-Hedging terisolasi per mode (Mode B tidak ganggu Mode C, keduanya tidak ganggu manual)
    else if ((direction == "long" && mode_sells > 0) || (direction == "short" && mode_buys > 0))
    {
        Print("Kronos [", comment, "]: Melewati ", direction, " ", pair, " (ada posisi lawan arah di mode ini).");
        order_placed = true;
    }
    else if (total_mode_pos >= MaxPositionsPerMode)
    {
        Print("Kronos [", comment, "]: Maksimal ", MaxPositionsPerMode, " posisi untuk ", pair, " di mode ini tercapai.");
        order_placed = true;
    }
    else if (direction == "long")
    {
        if (bid > 0 && stop >= bid && stop > 0)
            stop = NormalizeDouble(bid - 150 * point, digits);

        if (trade.Buy(lot_size, pair, 0, stop, target, comment))
        {
            ticket = (long)trade.ResultOrder();
            order_placed = true;
            Print("Kronos [", comment, "]: BUY dibuka (Layer #", total_mode_pos + 1, ") di ", ask, ". Ticket=", ticket);
        }
        else
        {
            Print("Kronos [", comment, "]: Gagal BUY ", pair, "! Error: ", trade.ResultRetcode(), " - ", trade.ResultRetcodeDescription());
        }
    }
    else if (direction == "short")
    {
        if (ask > 0 && stop <= ask && stop > 0)
            stop = NormalizeDouble(ask + 150 * point, digits);

        if (trade.Sell(lot_size, pair, 0, stop, target, comment))
        {
            ticket = (long)trade.ResultOrder();
            order_placed = true;
            Print("Kronos [", comment, "]: SELL dibuka (Layer #", total_mode_pos + 1, ") di ", bid, ". Ticket=", ticket);
        }
        else
        {
            Print("Kronos [", comment, "]: Gagal SELL ", pair, "! Error: ", trade.ResultRetcode(), " - ", trade.ResultRetcodeDescription());
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
