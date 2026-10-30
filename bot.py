import os
import json
import time
import requests
import pandas as pd
import numpy as np
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ==================== الإعدادات والمفاتيح ====================
TICKERALL_API_KEY = os.environ.get("TICKERALL_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TELEGRAM_GROUP_CHAT_ID = os.environ.get("TELEGRAM_GROUP_CHAT_ID")
MT5_PASSWORD = os.environ.get("MT5_PASSWORD")
MT5_SERVER = os.environ.get("MT5_SERVER")
MT5_ACCOUNT = os.environ.get("MT5_ACCOUNT")

STATE_FILE = "state.json"
MOSUL_TZ = ZoneInfo("Asia/Baghdad")
NY_TZ = ZoneInfo("America/New_York")
BASE_URL = "https://api.tickerall.com"
SERVER_OFFSET_HOURS = 3

# ==================== ثوابت الاستراتيجية ====================
MULT = 10.0
MIN_SL_PTS = 40.0
MAX_SL_PTS = 130.0
SL_BUF_PTS = 10.0
COOLDOWN_BARS = 10
MAX_BARS_TRADE = 60
TP1_PTS = 100.0
TP2_PTS = 150.0
TP3_PTS = 200.0
SYMBOL = "XAUUSD#"

# 🔴 ضع هنا IDs الستيكرات (إذا لم تتوفر اتركها فارغة)
STICKER_NEW_TRADE = "" 
STICKER_TP = ""
STICKER_SL = ""

def fmt_mosul_12h(dt_utc):
    """توقيت الموصل بنظام 12 ساعة"""
    return dt_utc.astimezone(MOSUL_TZ).strftime('%I:%M %p')

# ==================== رسائل التليجرام ====================
def send_telegram_raw(message):
    chat_ids = [c for c in [TELEGRAM_CHAT_ID, TELEGRAM_GROUP_CHAT_ID] if c]
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=15)
        except Exception as e:
            print(f"TG Error: {e}")

def send_sticker(sticker_id):
    if not sticker_id: return
    chat_ids = [c for c in [TELEGRAM_CHAT_ID, TELEGRAM_GROUP_CHAT_ID] if c]
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendSticker"
        try:
            requests.post(url, json={"chat_id": chat_id, "sticker": sticker_id}, timeout=15)
        except Exception as e:
            print(f"Sticker Error: {e}")

def send_new_trade_msg(trade):
    direction_icon = "🟢 <b>BUY</b>" if trade["direction"] == "BUY" else "🔴 <b>SELL</b>"
    msg = (
        f"🚀 <b>صفقة جديدة!</b> 🚀\n\n"
        f"📊 <b>النموذج:</b> {trade['model']}\n"
        f"📈 <b>الاتجاه:</b> {direction_icon}\n"
        f"💰 <b>الدخول:</b> <code>{trade['entry']}</code>\n"
        f"🚫 <b>الستوب:</b> <code>{trade['sl']}</code> (مخاطرة {trade['risk_pts']:.1f} نقطة)\n\n"
        f"🎯 <b>الهدف الأول:</b> <code>{trade['tp1']}</code>\n"
        f"🎯🎯 <b>الهدف الثاني:</b> <code>{trade['tp2']}</code>\n"
        f"🎯🎯🎯 <b>الهدف الثالث:</b> <code>{trade['tp3']}</code>\n\n"
        f"⏰ <b>الوقت:</b> {fmt_mosul_12h(datetime.now(ZoneInfo('UTC')))}\n"
    )
    send_telegram_raw(msg)
    send_sticker(STICKER_NEW_TRADE)

def send_update_msg(trade, event, current_price=None):
    model = trade['model']
    e = trade['entry']
    now_str = fmt_mosul_12h(datetime.now(ZoneInfo('UTC')))
    
    if event == "TP1":
        msg = f"✅ <b>ضرب الهدف الأول!</b> 🎯\n\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>\n🛡️ <b>تم نقل الستوب إلى نقطة الدخول (BE)</b>\n⏰ {now_str}"
        send_sticker(STICKER_TP)
    elif event == "TP2":
        msg = f"✅ <b>ضرب الهدف الثاني!</b> 🎯🎯\n\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>\n⏰ {now_str}"
        send_sticker(STICKER_TP)
    elif event == "TP3":
        msg = f"🏆 <b>ضرب الهدف الثالث!</b> 🎯🎯🎯\n\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>\n🎉 مبروك الأرباح الكاملة!"
        send_sticker(STICKER_TP)
    elif event == "SL":
        msg = f"❌ <b>ضرب الستوب!</b> 🚫\n\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>\n⏰ {now_str}"
        send_sticker(STICKER_SL)
    elif event == "BE":
        msg = f"🛡️ <b>ضرب الستوب بعد الهدف الأول (Break Even)</b>\n\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>"
        send_sticker(STICKER_SL)
    elif event == "TIME":
        msg = f"⏳ <b>إغلاق الصفقة (Time Exit)</b>\n\n📊 <b>النموذج:</b> {model}\n💰 <b>السعر الحالي:</b> <code>{current_price}</code>"
    
    send_telegram_raw(msg)

# ==================== دوال جلب البيانات ====================
def open_session(max_retries=3):
    url = BASE_URL + "/v1/sessions"
    headers = {"Authorization": "Bearer " + TICKERALL_API_KEY, "Content-Type": "application/json"}
    payload = {
        "broker": "mt5", "server": MT5_SERVER,
        "account": int(MT5_ACCOUNT) if MT5_ACCOUNT and MT5_ACCOUNT.isdigit() else MT5_ACCOUNT,
        "password": MT5_PASSWORD
    }
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Session attempt {attempt}/{max_retries}...", flush=True)
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            if r.status_code == 200:
                account_id = r.json().get("accountId")
                print(f"Session opened: {account_id}", flush=True)
                return account_id
            else:
                print(f"Session failed: {r.status_code} {r.text[:200]}", flush=True)
                if attempt < max_retries: time.sleep(5)
        except Exception as e:
            print(f"Session error: {e}", flush=True)
            if attempt < max_retries: time.sleep(5)
    return None

def fetch_candles(account_id, timeframe, limit=500, hours=500):
    url = BASE_URL + f"/v1/accounts/{account_id}/candles"
    headers = {"Authorization": "Bearer " + TICKERALL_API_KEY}
    params = {"symbol": SYMBOL, "timeframe": timeframe, "limit": limit, "hours": hours}
    try:
        print(f"Fetching {timeframe}...", flush=True)
        r = requests.get(url, headers=headers, params=params, timeout=90)
        print(f"{timeframe} HTTP Status: {r.status_code}", flush=True)
        if r.status_code != 200:
            print(f"Fail {timeframe}: {r.status_code} {r.text[:100]}", flush=True)
            return None
        data = r.json()
        candles = data.get("candles", [])
        if not candles:
            print(f"No candles for {timeframe}", flush=True)
            return None
        df = pd.DataFrame(candles)
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True) - pd.Timedelta(hours=SERVER_OFFSET_HOURS)
        df = df[["datetime", "open", "high", "low", "close"]].copy()
        for c in ["open", "high", "low", "close"]:
            df[c] = pd.to_numeric(df[c])
        df = df.sort_values("datetime").reset_index(drop=True)
        print(f"OK {timeframe}: {len(df)} candles | last: {df.iloc[-1]['close']}", flush=True)
        return df
    except Exception as e:
        print(f"Fetch {timeframe} Error: {e}", flush=True)
        traceback.print_exc()
        return None

# ==================== دوال الحسابات الفنية ====================
def ta_atr(df, period=14):
    tr = pd.concat([df["high"] - df["low"], (df["high"] - df["close"].shift(1)).abs(), (df["low"] - df["close"].shift(1)).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0/period, adjust=False).mean()

def ta_ema(series, length):
    return series.ewm(span=length, adjust=False).mean()

def ta_pivothigh(highs, left, right):
    n = len(highs); res = np.full(n, np.nan)
    for i in range(left, n - right):
        window = highs[i-left:i+right+1]
        if highs[i] == window.max() and (window == highs[i]).sum() == 1:
            res[i + right] = highs[i]
    return res

def ta_pivotlow(lows, left, right):
    n = len(lows); res = np.full(n, np.nan)
    for i in range(left, n - right):
        window = lows[i-left:i+right+1]
        if lows[i] == window.min() and (window == lows[i]).sum() == 1:
            res[i + right] = lows[i]
    return res

def session_flags(dt):
    t = dt.hour * 60 + dt.minute
    def tm(h1, m1, h2, m2): return (h1*60+m1) <= t < (h2*60+m2)
    return {
        "LondonO": tm(2, 0, 3, 0), "SB-LDN": tm(3, 0, 4, 0), "Judas": tm(9, 30, 10, 0),
        "SB-AM": tm(10, 0, 11, 0), "2022-AM": tm(11, 0, 11, 30), "Lunch": tm(11, 50, 12, 10),
        "SB-PM": tm(14, 0, 15, 0), "MOC": tm(15, 15, 15, 45), "FOMC": tm(14, 0, 14, 30),
        "NFP": tm(8, 30, 9, 0), "TGIF": dt.weekday() == 4 and tm(14, 0, 15, 0)
    }

# ==================== المنطق الأساسي للاستراتيجية ====================
def check_all_models(df_m30, df_h1, now_utc, now_ny):
    n = len(df_m30)
    if n < 50: return []
    
    atr = ta_atr(df_m30, 14).values
    sh = ta_pivothigh(df_m30["high"].values, 3, 3)
    sl = ta_pivotlow(df_m30["low"].values, 3, 3)
    
    last_sh = np.full(n, np.nan); last_sl = np.full(n, np.nan)
    cur_sh = np.nan; cur_sl = np.nan
    for i in range(n):
        if not np.isnan(sh[i]): cur_sh = sh[i]
        if not np.isnan(sl[i]): cur_sl = sl[i]
        last_sh[i] = cur_sh; last_sl[i] = cur_sl

    recent_low = df_m30["low"].rolling(20).min().shift(1).values
    recent_high = df_m30["high"].rolling(20).max().shift(1).values
    bull_sweep = (df_m30["low"].values < recent_low) & (df_m30["close"].values > recent_low)
    bear_sweep = (df_m30["high"].values > recent_high) & (df_m30["close"].values < recent_high)
    
    o = df_m30["open"].values; h = df_m30["high"].values; l = df_m30["low"].values; c = df_m30["close"].values
    
    bSweepOK = np.zeros(n, dtype=bool); sSweepOK = np.zeros(n, dtype=bool)
    bSweepLow = np.full(n, np.nan); sSweepHigh = np.full(n, np.nan)
    bFVG = np.zeros(n, dtype=bool); sFVG = np.zeros(n, dtype=bool)
    bTop = np.full(n, np.nan); bBot = np.full(n, np.nan)
    sTop = np.full(n, np.nan); sBot = np.full(n, np.nan)
    bOB = np.zeros(n, dtype=bool); sOB = np.zeros(n, dtype=bool)
    bOBH = np.full(n, np.nan); bOBL = np.full(n, np.nan); bOBMT = np.full(n, np.nan)
    sOBH = np.full(n, np.nan); sOBL = np.full(n, np.nan); sOBMT = np.full(n, np.nan)
    bMit = np.zeros(n, dtype=bool); sMit = np.zeros(n, dtype=bool)
    bMitH = np.full(n, np.nan); bMitL = np.full(n, np.nan); bMitCE = np.full(n, np.nan)
    sMitH = np.full(n, np.nan); sMitL = np.full(n, np.nan); sMitCE = np.full(n, np.nan)
    bull_mss = np.zeros(n, dtype=bool); bear_mss = np.zeros(n, dtype=bool)
    
    cbS = False; cbSBar = -1; cbSL = np.nan
    csS = False; csSBar = -1; csSH = np.nan
    cbM = False; cbMBar = -1; csM = False; csMBar = -1
    cbF = False; cbFBar = -1; cbT = np.nan; cbB = np.nan
    csF = False; csFBar = -1; csT = np.nan; csB = np.nan
    cbO = False; cbOBar = -1; cbOH = np.nan; cbOL = np.nan; cbOMT = np.nan
    csO = False; csOBar = -1; csOH = np.nan; csOL = np.nan; csOMT = np.nan
    cbM_ = False; cbMBar_ = -1; cbMH = np.nan; cbML = np.nan
    csM_ = False; csMBar_ = -1; csMH = np.nan; csML = np.nan

    for i in range(2, n):
        # Sweeps
        if bull_sweep[i]: cbS = True; cbSBar = i; cbSL = l[i]
        if bear_sweep[i]: csS = True; csSBar = i; csSH = h[i]
        if cbS and (i - cbSBar) > 20: cbS = False
        if csS and (i - csSBar) > 20: csS = False
        bSweepOK[i] = cbS; bSweepLow[i] = cbSL
        sSweepOK[i] = csS; sSweepHigh[i] = csSH
        
        # MSS
        if not np.isnan(last_sh[i]) and c[i] > last_sh[i] and c[i-1] <= last_sh[i] and bSweepOK[i]: cbM = True; cbMBar = i
        if not np.isnan(last_sl[i]) and c[i] < last_sl[i] and c[i-1] >= last_sl[i] and sSweepOK[i]: csM = True; csMBar = i
        if cbM and (i - cbMBar) > 15: cbM = False
        if csM and (i - csMBar) > 15: csM = False
        bull_mss[i] = cbM; bear_mss[i] = csM
        
        # FVG
        if l[i] > h[i-2]: cbF = True; cbFBar = i; cbT = l[i]; cbB = h[i-2]
        if h[i] < l[i-2]: csF = True; csFBar = i; csT = l[i-2]; csB = h[i]
        if cbF and (i - cbFBar) > 15: cbF = False
        if csF and (i - csFBar) > 15: csF = False
        bFVG[i] = cbF; bTop[i] = cbT; bBot[i] = cbB
        sFVG[i] = csF; sTop[i] = csT; sBot[i] = csB
        
        # OB
        if c[i] > o[i] and c[i-1] < o[i-1]: cbO = True; cbOBar = i-1; cbOH = h[i-1]; cbOL = l[i-1]; cbOMT = (o[i-1]+c[i-1])/2.0
        if c[i] < o[i] and c[i-1] > o[i-1]: csO = True; csOBar = i-1; csOH = h[i-1]; csOL = l[i-1]; csOMT = (o[i-1]+c[i-1])/2.0
        if cbO and (i - cbOBar) > 15: cbO = False
        if csO and (i - csOBar) > 15: csO = False
        bOB[i] = cbO; bOBH[i] = cbOH; bOBL[i] = cbOL; bOBMT[i] = cbOMT
        sOB[i] = csO; sOBH[i] = csOH; sOBL[i] = csOL; sOBMT[i] = csOMT

        # Mitigation
        if c[i] > o[i] and c[i-1] < o[i-1] and c[i] > h[i-2]: cbM_ = True; cbMBar_ = i-1; cbMH = h[i-1]; cbML = l[i-1]
        if c[i] < o[i] and c[i-1] > o[i-1] and c[i] < l[i-2]: csM_ = True; csMBar_ = i-1; csMH = h[i-1]; csML = l[i-1]
        if cbM_ and (i - cbMBar_) > 15: cbM_ = False
        if csM_ and (i - csMBar_) > 15: csM_ = False
        bMit[i] = cbM_; bMitH[i] = cbMH; bMitL[i] = cbML; bMitCE[i] = (cbMH + cbML)/2
        sMit[i] = csM_; sMitH[i] = csMH; sMitL[i] = csML; sMitCE[i] = (csMH + csML)/2

    # HTF Trend
    df_h1["ema200"] = ta_ema(df_h1["close"], 200)
    df_h1["ema50"] = ta_ema(df_h1["close"], 50)
    h1 = df_h1.iloc[-2]
    trendUp = h1["close"] > h1["ema200"] if not pd.isna(h1["ema200"]) else False
    trendDown = h1["close"] < h1["ema200"] if not pd.isna(h1["ema200"]) else False
    strongBull = trendUp and not pd.isna(h1["ema50"]) and h1["close"] > h1["ema50"]
    strongBear = trendDown and not pd.isna(h1["ema50"]) and h1["close"] < h1["ema50"]

    sessions = session_flags(now_ny)
    anyKZ = any([sessions[k] for k in ["LondonO","SB-LDN","Judas","SB-AM","2022-AM","Lunch","SB-PM","MOC","FOMC","NFP","TGIF"]])
    t_min = now_ny.hour * 60 + now_ny.minute
    inLunchBl = 12*60+10 <= t_min < 13*60+59
    sessKZ = anyKZ and not inLunchBl
    inAMKZ = sessions["SB-AM"] or sessions["Judas"]
    
    i = n - 1
    a14 = atr[i]
    swingEq = (last_sh[i] + last_sl[i]) / 2.0 if not (np.isnan(last_sh[i]) or np.isnan(last_sl[i])) else np.nan
    
    signals = []
    
    # 1. IOFED
    if sessKZ and (bull_mss[i] or bSweepOK[i]) and bOB[i] and l[i] <= bOBMT[i] and l[i] >= bOBL[i] and c[i] > o[i] and not np.isnan(swingEq) and bOBMT[i] < swingEq and trendUp and (c[i]-o[i]) > a14*0.4:
        signals.append({"model": "IOFED", "dir": "BUY", "entry": bOBMT[i], "sl": bOBL[i]-a14*0.3})
    if sessKZ and (bear_mss[i] or sSweepOK[i]) and sOB[i] and h[i] >= sOBMT[i] and h[i] <= sOBH[i] and c[i] < o[i] and not np.isnan(swingEq) and sOBMT[i] > swingEq and trendDown and (o[i]-c[i]) > a14*0.4:
        signals.append({"model": "IOFED", "dir": "SELL", "entry": sOBMT[i], "sl": sOBH[i]+a14*0.3})

    # 2. FVG-Direct
    bFage = i - np.where(bFVG)[0][-1] if bFVG.any() else 999
    sFage = i - np.where(sFVG)[0][-1] if sFVG.any() else 999
    if sessKZ and strongBull and bFVG[i] and bFage <= 5 and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2 and c[i] > bBot[i] and abs(c[i]-o[i]) > a14*0.3:
        signals.append({"model": "FVG-Direct", "dir": "BUY", "entry": (bTop[i]+bBot[i])/2, "sl": bBot[i]-a14*0.3})
    if sessKZ and strongBear and sFVG[i] and sFage <= 5 and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2 and c[i] < sTop[i] and abs(c[i]-o[i]) > a14*0.3:
        signals.append({"model": "FVG-Direct", "dir": "SELL", "entry": (sTop[i]+sBot[i])/2, "sl": sTop[i]+a14*0.3})

    # 3. OB-Pro
    if sessKZ and strongBull and bOB[i] and (i - cbOBar) <= 10 and bull_mss[i] and not np.isnan(swingEq) and bOBMT[i] < swingEq and l[i] <= bOBMT[i] and l[i] >= bOBL[i] and c[i] > o[i] and c[i] > bOBMT[i]:
        signals.append({"model": "OB-Pro", "dir": "BUY", "entry": bOBMT[i], "sl": bOBL[i]-a14*0.3})
    if sessKZ and strongBear and sOB[i] and (i - csOBar) <= 10 and bear_mss[i] and not np.isnan(swingEq) and sOBMT[i] > swingEq and h[i] >= sOBMT[i] and h[i] <= sOBH[i] and c[i] < o[i] and c[i] < sOBMT[i]:
        signals.append({"model": "OB-Pro", "dir": "SELL", "entry": sOBMT[i], "sl": sOBH[i]+a14*0.3})

    # 4. SMR
    if sessKZ and sSweepOK[i] and bull_mss[i] and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2 and (c[i]-o[i]) > a14*0.5:
        signals.append({"model": "SMR", "dir": "BUY", "entry": (bTop[i]+bBot[i])/2, "sl": bBot[i]-a14*0.3})
    if sessKZ and bSweepOK[i] and bear_mss[i] and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2 and (o[i]-c[i]) > a14*0.5:
        signals.append({"model": "SMR", "dir": "SELL", "entry": (sTop[i]+sBot[i])/2, "sl": sTop[i]+a14*0.3})

    # 5. Mitigation
    if sessKZ and strongBull and bMit[i] and (i - cbMBar_) <= 8 and l[i] <= bMitCE[i] and l[i] >= bMitL[i] and c[i] > o[i] and c[i] > bMitCE[i] and (c[i]-o[i]) > a14*0.4:
        signals.append({"model": "Mitigation", "dir": "BUY", "entry": bMitCE[i], "sl": bMitL[i]-a14*0.3})
    if sessKZ and strongBear and sMit[i] and (i - csMBar_) <= 8 and h[i] >= sMitCE[i] and h[i] <= sMitH[i] and c[i] < o[i] and c[i] < sMitCE[i] and (o[i]-c[i]) > a14*0.4:
        signals.append({"model": "Mitigation", "dir": "SELL", "entry": sMitCE[i], "sl": sMitH[i]+a14*0.3})

    # 6. MMBM
    if inAMKZ and bSweepOK[i] and bull_mss[i] and bOB[i] and l[i] <= bOBMT[i] and l[i] >= bOBL[i] and not np.isnan(swingEq) and bOBMT[i] < swingEq and trendUp:
        signals.append({"model": "MMBM", "dir": "BUY", "entry": bOBMT[i], "sl": bOBL[i]-a14*0.3})

    # 7. 2022
    if sessions["SB-AM"] and bSweepOK[i] and bull_mss[i] and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and l[i] >= bBot[i] and trendUp:
        signals.append({"model": "2022", "dir": "BUY", "entry": (bTop[i]+bBot[i])/2, "sl": bBot[i]-a14*0.3})
    if sessions["SB-AM"] and sSweepOK[i] and bear_mss[i] and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and h[i] <= sTop[i] and trendDown:
        signals.append({"model": "2022", "dir": "SELL", "entry": (sTop[i]+sBot[i])/2, "sl": sTop[i]+a14*0.3})

    # 8. Reaper (Sell only)
    if sessKZ and strongBear and not np.isnan(swingEq) and c[i] > swingEq and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and h[i] <= sTop[i] and c[i] < o[i]:
        signals.append({"model": "Reaper", "dir": "SELL", "entry": (sTop[i]+sBot[i])/2, "sl": sTop[i]+a14*0.3})

    # 9. SBPM-MSS
    if sessions["SB-PM"] and bull_mss[i] and bFVG[i] and trendUp:
        signals.append({"model": "SBPM-MSS", "dir": "BUY", "entry": (bTop[i]+bBot[i])/2, "sl": bSweepLow[i]-a14*0.3})
    if sessions["SB-PM"] and bear_mss[i] and sFVG[i] and trendDown:
        signals.append({"model": "SBPM-MSS", "dir": "SELL", "entry": (sTop[i]+sBot[i])/2, "sl": sSweepHigh[i]+a14*0.3})

    # 10. Judas
    if sessions["Judas"] and trendUp and bull_sweep[i] and c[i] > o[i]:
        signals.append({"model": "Judas", "dir": "BUY", "entry": c[i], "sl": recent_low[i]-a14*0.3})
    if sessions["Judas"] and trendDown and bear_sweep[i] and c[i] < o[i]:
        signals.append({"model": "Judas", "dir": "SELL", "entry": c[i], "sl": recent_high[i]+a14*0.3})

    # 11. TGIF
    if sessions["TGIF"] and trendDown and bull_sweep[i] and c[i] > o[i]:
        signals.append({"model": "TGIF", "dir": "BUY", "entry": c[i], "sl": recent_low[i]-a14*0.3})
    if sessions["TGIF"] and trendUp and bear_sweep[i] and c[i] < o[i]:
        signals.append({"model": "TGIF", "dir": "SELL", "entry": c[i], "sl": recent_high[i]+a14*0.3})

    # فلترة الإشارات وحساب الأهداف
    valid_signals = []
    for sig in signals:
        risk = abs(sig["entry"] - sig["sl"]) * MULT
        if MIN_SL_PTS <= risk <= MAX_SL_PTS:
            if sig["dir"] == "BUY":
                sig["tp1"] = round(sig["entry"] + TP1_PTS/MULT, 2)
                sig["tp2"] = round(sig["entry"] + TP2_PTS/MULT, 2)
                sig["tp3"] = round(sig["entry"] + TP3_PTS/MULT, 2)
            else:
                sig["tp1"] = round(sig["entry"] - TP1_PTS/MULT, 2)
                sig["tp2"] = round(sig["entry"] - TP2_PTS/MULT, 2)
                sig["tp3"] = round(sig["entry"] - TP3_PTS/MULT, 2)
            sig["risk_pts"] = risk
            valid_signals.append(sig)
            
    return valid_signals

# ==================== إدارة الصفقات ====================
def manage_active_trades(state, current_price, now_utc):
    if "active_trades" not in state: state["active_trades"] = []
    
    for trade in state["active_trades"][:]:
        d = trade["direction"]
        e = trade["entry"]
        tp1 = trade["tp1"]; tp2 = trade["tp2"]; tp3 = trade["tp3"]
        
        entry_time = datetime.fromisoformat(trade["entry_time"])
        bars_elapsed = (now_utc - entry_time).total_seconds() / 1800 
        
        if bars_elapsed >= MAX_BARS_TRADE:
            print(f"Time Exit for {trade['model']}")
            send_update_msg(trade, "TIME", current_price)
            state["active_trades"].remove(trade)
            continue

        if d == "BUY":
            if not trade["tp1_hit"] and current_price >= tp1:
                trade["tp1_hit"] = True; trade["sl"] = e
                print(f"TP1 Hit for {trade['model']}")
                send_update_msg(trade, "TP1")
            if trade["tp1_hit"] and not trade["tp2_hit"] and current_price >= tp2:
                trade["tp2_hit"] = True
                print(f"TP2 Hit for {trade['model']}")
                send_update_msg(trade, "TP2")
            if trade["tp2_hit"] and not trade["tp3_hit"] and current_price >= tp3:
                print(f"TP3 Hit for {trade['model']}")
                send_update_msg(trade, "TP3")
                state["active_trades"].remove(trade); continue
            if current_price <= trade["sl"]:
                event = "BE" if trade["tp1_hit"] else "SL"
                print(f"{event} Hit for {trade['model']}")
                send_update_msg(trade, event)
                state["active_trades"].remove(trade); continue
                
        elif d == "SELL":
            if not trade["tp1_hit"] and current_price <= tp1:
                trade["tp1_hit"] = True; trade["sl"] = e
                print(f"TP1 Hit for {trade['model']}")
                send_update_msg(trade, "TP1")
            if trade["tp1_hit"] and not trade["tp2_hit"] and current_price <= tp2:
                trade["tp2_hit"] = True
                print(f"TP2 Hit for {trade['model']}")
                send_update_msg(trade, "TP2")
            if trade["tp2_hit"] and not trade["tp3_hit"] and current_price <= tp3:
                print(f"TP3 Hit for {trade['model']}")
                send_update_msg(trade, "TP3")
                state["active_trades"].remove(trade); continue
            if current_price >= trade["sl"]:
                event = "BE" if trade["tp1_hit"] else "SL"
                print(f"{event} Hit for {trade['model']}")
                send_update_msg(trade, event)
                state["active_trades"].remove(trade); continue

# ==================== المحرك الرئيسي ====================
def main():
    print("Starting ICT Gold v28 Elite Bot...", flush=True)
    
    # تحميل الحالة مع التوافق مع الملف القديم
    state = {"active_trades": [], "last_day": "", "last_entry_times": {}}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f: 
                loaded = json.load(f)
                if "active_trades" not in loaded: loaded["active_trades"] = []
                if "last_entry_times" not in loaded: loaded["last_entry_times"] = {}
                state = loaded
        except Exception as e:
            print(f"State load error: {e}", flush=True)

    now_utc = datetime.now(ZoneInfo("UTC"))
    now_ny = now_utc.astimezone(NY_TZ)
    
    today = now_ny.date().isoformat()
    if state.get("last_day") != today:
        state["last_day"] = today
        state["last_entry_times"] = {}
        
    if now_ny.weekday() >= 5:
        print("Weekend - bot sleeping", flush=True)
        with open(STATE_FILE, 'w') as f: json.dump(state, f, indent=2)
        return

    print("Opening session...", flush=True)
    account_id = open_session()
    if not account_id:
        print("Failed to open session. Exiting.", flush=True)
        return

    print("Fetching M30 data...", flush=True)
    df_m30 = fetch_candles(account_id, "M30", 500, 500)
    if df_m30 is None:
        print("Failed to fetch M30 data. Exiting.", flush=True)
        return
        
    print("Fetching H1 data...", flush=True)
    df_h1 = fetch_candles(account_id, "H1", 500, 500)
    if df_h1 is None:
        print("Failed to fetch H1 data. Exiting.", flush=True)
        return

    current_price = float(df_m30.iloc[-1]["close"])
    print(f"Current Price: {current_price} | Time: {fmt_mosul_12h(now_utc)}", flush=True)

    # 1. إدارة الصفقات المفتوحة
    manage_active_trades(state, current_price, now_utc)

    # 2. إشارات جديدة
    print("Checking signals...", flush=True)
    signals = check_all_models(df_m30, df_h1, now_utc, now_ny)
    print(f"Signals found: {len(signals)}", flush=True)
    
    for sig in signals:
        model_name = sig["model"]
        
        # فحص الـ Cooldown (10 شمعات = 5 ساعات تقريباً)
        last_entry = state.get("last_entry_times", {}).get(model_name)
        if last_entry:
            last_dt = datetime.fromisoformat(last_entry)
            if (now_utc - last_dt).total_seconds() / 1800 < COOLDOWN_BARS:
                print(f"Cooldown active for {model_name}", flush=True)
                continue

        # فحص إذا كان النموذج عنده صفقة مفتوحة حالياً
        is_active = any(t["model"] == model_name for t in state["active_trades"])
        if is_active:
            print(f"Trade already active for {model_name}", flush=True)
            continue

        trade_record = {
            "model": model_name, "direction": sig["dir"],
            "entry": round(sig["entry"], 2), "sl": round(sig["sl"], 2),
            "tp1": sig["tp1"], "tp2": sig["tp2"], "tp3": sig["tp3"],
            "risk_pts": sig["risk_pts"], "entry_time": now_utc.isoformat(),
            "tp1_hit": False, "tp2_hit": False, "tp3_hit": False
        }
        
        state["active_trades"].append(trade_record)
        state["last_entry_times"][model_name] = now_utc.isoformat()
        send_new_trade_msg(trade_record)
        print(f"✅ New Trade: {model_name} {sig['dir']} @ {sig['entry']}", flush=True)

    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"FATAL ERROR: {e}", flush=True)
        traceback.print_exc()