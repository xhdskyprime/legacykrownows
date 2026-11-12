# PANDUAN DEPLOY KRONOS AI KE SERVER / VPS (WINDOWS)

Panduan lengkap menjalankan sistem trading otomatis Kronos AI 24/7 di VPS (Virtual Private Server).

---

## 💻 1. Spesifikasi VPS yang Disarankan
- **Sistem Operasi:** Windows Server (2019/2022) atau Windows 10/11 Pro 64-bit.
- **CPU:** Minimal 2 - 4 vCPU.
- **RAM:** Minimal 4 GB.
- **Storage:** 40 GB SSD.
- *(Rekomendasi provider murah: Contabo, Vultr, Kamatera, atau VPS gratisan dari broker seperti Exness/FBS).*

---

## 🚀 2. Langkah Setup di VPS (Hanya Dilakukan Sekali)

### Langkah A: Install Software Pendukung di VPS
1. **MetaTrader 5:** Download dan install MT5 dari broker Anda (misal: Exness MT5).
   - Buka MT5, login ke akun trading Anda.
   - Aktifkan tombol **"Algo Trading"** di toolbar atas (pastikan berwarna hijau).
2. **Git for Windows:** Download dan install dari `https://git-scm.com/download/win`.
3. **Python (versi 3.10 s/d 3.14 64-bit):** Download dari `https://www.python.org/downloads/windows/`.
   - ⚠️ **PENTING:** Saat install, centang kotak **"Add Python to PATH"**.

---

### Langkah B: Clone Repository & Dependency
Buka **Command Prompt (CMD)** atau **PowerShell** di VPS, lalu jalankan:

```bash
# 1. Pindah ke drive yang diinginkan (contoh: C:\ atau D:\)
cd C:\

# 2. Clone repository Anda
git clone https://github.com/xhdskyprime/legacykrownows.git
cd legacykrownows

# 3. Clone core library Kronos Foundation Model
git clone https://github.com/shiyu-coder/Kronos.git

# 4. Install seluruh library Python yang dibutuhkan
pip install -r requirements.txt
```

---

### Langkah C: Pasang & Kompilasi EA di MetaTrader 5 VPS
1. Buka MetaTrader 5 di VPS.
2. Klik menu **File** -> **Open Data Folder**.
3. Masuk ke folder **`MQL5`** -> **`Experts`** -> **`Advisors`**.
4. Copy file **`src/KronosEA.mq5`** dari folder `legacykrownows` ke dalam folder `Advisors` tersebut.
5. Tekan tombol **F4** di MT5 untuk membuka **MetaEditor**:
   - Di panel kiri Navigator MetaEditor, buka `Experts` -> `Advisors` -> klik 2x `KronosEA.mq5`.
   - Klik tombol **Compile** (atau tekan **F7**).
   - Pastikan hasilnya: `0 errors`. File `KronosEA.ex5` sekarang sudah siap.
6. Kembali ke MetaTrader 5:
   - Buka sembarang chart (misal: `XAUUSD` H1).
   - Di panel Navigator MT5, drag **`KronosEA`** ke atas chart.
   - Di tab **Common**, centang **"Allow Algo Trading"**.
   - Klik **OK**. Di pojok kanan atas chart akan muncul nama `KronosEA` dengan ikon topi biru tersenyum.

---

## ⚡ 3. Menjalankan Autopilot 24/7 di VPS

Buka Command Prompt (CMD) di VPS, arahkan ke folder project:

```bash
cd C:\legacykrownows
python run_autopilot.py
```

Sistem akan langsung memuat model AI Kronos, mendeteksi MetaTrader 5 yang menyala, dan mulai memindai pasar serta mengeksekusi order 24/7 secara mandiri!

### 💡 Tips Menjalankan di Background VPS (Supaya Tidak Tertutup saat RDP Ditutup):
Buat file `start_bot.bat`:
```bat
@echo off
cd /d %~dp0
python run_autopilot.py
pause
```
Cukup klik 2x `start_bot.bat`, lalu minimize remote desktop (jangan sign out). Bot akan terus berjalan 24 jam non-stop!

