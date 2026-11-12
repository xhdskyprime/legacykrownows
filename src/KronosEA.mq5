//+------------------------------------------------------------------+
//| KronosEA.mq5                                                     |
//| Kronos Trading System — MT5 Multi-Position & Trailing Stop EA     |
//| Configured for 10-Pair Mega Setup (Max 5 Positions per Pair)     |
//+------------------------------------------------------------------+
#property copyright "Kronos Trading System"
#property version   "2.00"
#property strict

#include <Trade\Trade.mqh>

//── Input parameters ──────────────────────────────────────────────
input string SignalFile             = "signal.json";     // Signal file Python writes
input string AckFile                = "signal_ack.json"; // Acknowledgement file EA writes
input int    MaxPositionsPerSymbol  = 10;                // Maksimal posisi per pair (Layering s/d 10)
input bool   EnableTrailingStop     = true;              // Aktifkan Auto Trailing Stop & BEP

//── Trade object ──────────────────────────────────────────────────
CTrade trade;

//+------------------------------------------------------------------+
//| EA initialisation                                                |
//+------------------------------------------------------------------+
int OnInit()
{
    trade.SetExpertMagicNumber(108888);
    EventSetTimer(3); // Cek sinyal & trailing stop setiap 3 detik
    Print("KronosEA v2.0 (10-Pair Mega Setup) started. Watching: ", SignalFile);
    return INIT_SUCCEEDED;
}

//+------------------------------------------------------------------+
//| EA cleanup                                                       |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
    EventKillTimer();
    Print("KronosEA stopped.");
}

//+------------------------------------------------------------------+
//| Extract field helper                                             |
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
//| Trailing Stop & Break-Even Manager                               |
//| Automatically locks Break-Even at +1R and trails winning moves   |
//+------------------------------------------------------------------+
void ManageTrailingStop()
{
    if (!EnableTrailingStop) return;

    for (int i = PositionsTotal() - 1; i >= 0; i--)
    {
        ulong ticket = PositionGetTicket(i);
        if (ticket == 0) continue;

        string comment = PositionGetString(POSITION_COMMENT);
        if (StringFind(comment, "Kronos") < 0) continue; // Hanya kelola posisi milik Kronos

        string sym        = PositionGetString(POSITION_SYMBOL);
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

            // Jika sudah profit minimal 1x initial risk -> Aktifkan BEP & Trailing
            if (profit_dist >= initial_risk)
            {
                double trail_step = initial_risk * 0.75;
                double new_sl = NormalizeDouble(bid - trail_step, digits);
                double be_sl  = NormalizeDouble(open_price + (10 * point), digits);

                if (new_sl < be_sl) new_sl = be_sl; // Kunci minimal Break-Even (+10 point buffer)

                // Hanya modify jika SL baru lebih tinggi minimal 3 point dari SL lama
                if (new_sl > (curr_sl + 3 * point))
                {
                    trade.PositionModify(ticket, new_sl, curr_tp);
                    Print("KronosEA: Trailing SL dimajukan untuk BUY ", sym, " #", ticket, " --> ", new_sl);
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

                if (new_sl > be_sl) new_sl = be_sl; // Kunci minimal Break-Even

                if (curr_sl == 0 || new_sl < (curr_sl - 3 * point))
                {
                    trade.PositionModify(ticket, new_sl, curr_tp);
                    Print("KronosEA: Trailing SL dimajukan untuk SELL ", sym, " #", ticket, " --> ", new_sl);
                }
            }
        }
    }
}

//+------------------------------------------------------------------+
//| Main logic — check for signal file and act on it                 |
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

    Print("KronosEA: Sinyal diterima | pair=", pair, " dir=", direction,
          " lot=", lot_size, " TP=", target, " SL=", stop);

    // Hitung posisi yang sudah ada untuk pair ini
    int same_dir_count = 0;
    int opp_dir_count  = 0;

    for (int i = 0; i < PositionsTotal(); i++)
    {
        if (PositionGetSymbol(i) == pair)
        {
            long p_type = PositionGetInteger(POSITION_TYPE);
            if ((direction == "long" && p_type == POSITION_TYPE_BUY) ||
                (direction == "short" && p_type == POSITION_TYPE_SELL))
            {
                same_dir_count++;
            }
            else
            {
                opp_dir_count++;
            }
        }
    }

    long   ticket       = 0;
    bool   order_placed = false;

    if (direction == "flat")
    {
        order_placed = true;
    }
    else if (opp_dir_count > 0)
    {
        Print("KronosEA: Melewati sinyal ", direction, " ", pair, " karena masih ada posisi lawan arah yang aktif.");
        order_placed = true;
    }
    else if (same_dir_count >= MaxPositionsPerSymbol)
    {
        Print("KronosEA: Batas maksimal ", MaxPositionsPerSymbol, " posisi untuk ", pair, " tercapai. Melewati.");
        order_placed = true;
    }
    else if (direction == "long")
    {
        double bid = SymbolInfoDouble(pair, SYMBOL_BID);
        double point = SymbolInfoDouble(pair, SYMBOL_POINT);
        int digits = (int)SymbolInfoInteger(pair, SYMBOL_DIGITS);
        if (stop >= bid && stop > 0)
        {
            stop = NormalizeDouble(bid - 150 * point, digits);
        }

        if (trade.Buy(lot_size, pair, 0, stop, target, "Kronos"))
        {
            ticket = trade.ResultOrder();
            order_placed = true;
            Print("KronosEA: BUY berhasil dibuka (Layer #", same_dir_count + 1, "). Ticket=", ticket);
        }
        else
        {
            Print("KronosEA: BUY gagal! Error=", GetLastError(), " RetCode=", trade.ResultRetcode());
        }
    }
    else if (direction == "short")
    {
        double ask = SymbolInfoDouble(pair, SYMBOL_ASK);
        double point = SymbolInfoDouble(pair, SYMBOL_POINT);
        int digits = (int)SymbolInfoInteger(pair, SYMBOL_DIGITS);
        if (stop <= ask && stop > 0)
        {
            stop = NormalizeDouble(ask + 150 * point, digits);
        }

        if (trade.Sell(lot_size, pair, 0, stop, target, "Kronos"))
        {
            ticket = trade.ResultOrder();
            order_placed = true;
            Print("KronosEA: SELL berhasil dibuka (Layer #", same_dir_count + 1, "). Ticket=", ticket);
        }
        else
        {
            Print("KronosEA: SELL gagal! Error=", GetLastError(), " RetCode=", trade.ResultRetcode());
        }
    }

    if (!order_placed) return;

    // Tulis konfirmasi ke Python
    string ack = "{\n  \"status\": \"executed\",\n  \"order_ticket\": "
                 + IntegerToString(ticket) + "\n}\n";
    WriteFile(AckFile, ack);

    // Hapus file sinyal agar EA menunggu sinyal berikutnya
    FileDelete(SignalFile, FILE_COMMON);
}

//+------------------------------------------------------------------+
//| Timer event handler                                              |
//+------------------------------------------------------------------+
void OnTimer()
{
    ProcessSignalFile();
    ManageTrailingStop();
}
