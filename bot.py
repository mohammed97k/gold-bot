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

# ==================== ثوابت الاستراتيجية (مطابقة للباين) ====================
MULT = 10.0
ATR_PERIOD = 14
MIN_SL_PTS = 40.0
MAX_SL_PTS = 130.0
SL_BUF_PTS = 10.0
COOLDOWN_BARS = 10
MAX_BARS_TRADE = 60
TP1_PTS = 100.0
TP2_PTS = 150.0
TP3_PTS = 200.0
SYMBOL = "XAUUSD#"

# ترتيب النماذج الـ 11
MODEL_NAMES = ["IOFED", "FVG-Direct", "OB-Pro", "SMR", "Mitigation", "MMBM", "2022", "Reaper", "SBPM-MSS", "Judas", "TGIF"]
N_MODELS = 11

def fmt_mosul_12h(dt_utc):
    """توقيت الموصل بنظام 12 ساعة"""
    return dt_utc.astimezone(MOSUL_TZ).strftime('%I:%M %p')

# ==================== دوال التليجرام والرسائل ====================
def send_telegram_raw(message, parse_mode="HTML"):
    chat_ids = [c for c in [TELEGRAM_CHAT_ID, TELEGRAM_GROUP_CHAT_ID] if c]
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": parse_mode}, timeout=15)
        except Exception as e:
            print(f"TG Error: {e}")

def send_telegram_sticker(sticker_id):
    # ملاحظة: تضع هنا الـ file_id مال الستيكرات لاحقاً
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
    send_telegram_sticker("CAACAgQAAxkBAAIB...") # دزلي ID الستيكر هنا

def send_update_msg(trade, event):
    model = trade['model']
    d = trade['direction']
    e = trade['entry']
    if event == "TP1":
        msg = f"✅ <b>ضرب الهدف الأول!</b> 🎯\n\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>\n🛡️ <b>تم نقل الستوب إلى نقطة الدخول (BE)</b>\n⏰ {fmt_mosul_12h(datetime.now(ZoneInfo('UTC')))}"
    elif event == "TP2":
        msg = f"✅ <b>ضرب الهدف الثاني!</b> 🎯🎯\n\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>\n⏰ {fmt_mosul_12h(datetime.now(ZoneInfo('UTC')))}"
    elif event == "TP3":
        msg = f"🏆 <b>ضرب الهدف الثالث!</b> 🎯🎯🎯\n\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>\n🎉 مبروك الأرباح الكاملة!"
    elif event == "SL":
        msg = f"❌ <b>ضرب الستوب!</b> 🚫\n\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>\n⏰ {fmt_mosul_12h(datetime.now(ZoneInfo('UTC')))}"
    elif event == "BE":
        msg = f"🛡️ <b>ضرب الستوب بعد الهدف الأول (Break Even)</b>\n\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>"
    elif event == "TIME":
        msg = f"⏳ <b>إغلاق الصفقة (Time Exit)</b>\n\n📊 <b>النموذج:</b> {model}\n💰 <b>السعر الحالي:</b> <code>{trade['current_price']}</code>"
    
    send_telegram_raw(msg)
    send_telegram_sticker("CAACAgQAAxkBAAIB...") # دزلي ID الستيكر هنا

# ==================== دوال جلب البيانات ====================
def open_session():
    url = BASE_URL + "/v1/sessions"
    headers = {"Authorization": "Bearer " + TICKERALL_API_KEY, "Content-Type": "application/json"}
    payload = {
        "broker": "mt5", "server": MT5_SERVER,
        "account": int(MT5_ACCOUNT) if MT5_ACCOUNT and MT5_ACCOUNT.isdigit() else MT5_ACCOUNT,
        "password": MT5_PASSWORD
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=30)
        if r.status_code == 200: return r.json().get("accountId")
    except Exception as e:
        print(f"Session error: {e}")
    return None

def fetch_candles(account_id, timeframe, limit=500, hours=500):
    url = BASE_URL + f"/v1/accounts/{account_id}/candles"
    headers = {"Authorization": "Bearer " + TICKERALL_API_KEY}
    params = {"symbol": SYMBOL, "timeframe": timeframe, "limit": limit, "hours": hours}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=90)
        if r.status_code != 200: return None
        data = r.json()
        candles = data.get("candles", [])
        if not candles: return None
        df = pd.DataFrame(candles)
        df["datetime"] = pd.to_datetime(df["timestamp"], unit="s", utc=True) - pd.Timedelta(hours=SERVER_OFFSET_HOURS)
        df = df[["datetime", "open", "high", "low", "close"]].copy()
        for c in ["open", "high", "low", "close"]:
            df[c] = pd.to_numeric(df[c])
        return df.sort_values("datetime").reset_index(drop=True)
    except Exception as e:
        print(f"Fetch Error: {e}")
        return None

# ==================== دوال الحسابات الفنية (المطابقة للباين) ====================
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
def build_and_check_signals(df_m30, df_h1, now_utc, now_ny):
    n = len(df_m30)
    if n < 50: return []
    
    atr = ta_atr(df_m30, ATR_PERIOD).values
    sh = ta_pivothigh(df_m30["high"].values, 3, 3)
    sl = ta_pivotlow(df_m30["low"].values, 3, 3)
    
    last_sh = np.full(n, np.nan)
    last_sl = np.full(n, np.nan)
    cur_sh = np.nan; cur_sl = np.nan
    for i in range(n):
        if not np.isnan(sh[i]): cur_sh = sh[i]
        if not np.isnan(sl[i]): cur_sl = sl[i]
        last_sh[i] = cur_sh; last_sl[i] = cur_sl

    recent_low = df_m30["low"].rolling(20).min().shift(1).values
    recent_high = df_m30["high"].rolling(20).max().shift(1).values
    bull_sweep = (df_m30["low"].values < recent_low) & (df_m30["close"].values > recent_low)
    bear_sweep = (df_m30["high"].values > recent_high) & (df_m30["close"].values < recent_high)
    
    # FVG, OB, MSS Tracking
    bull_mss = np.zeros(n, dtype=bool); bear_mss = np.zeros(n, dtype=bool)
    bSweepOK = np.zeros(n, dtype=bool); sSweepOK = np.zeros(n, dtype=bool)
    bSweepLow = np.full(n, np.nan); sSweepHigh = np.full(n, np.nan)
    bFVG = np.zeros(n, dtype=bool); sFVG = np.zeros(n, dtype=bool)
    bTop = np.full(n, np.nan); bBot = np.full(n, np.nan)
    sTop = np.full(n, np.nan); sBot = np.full(n, np.nan)
    bOB = np.zeros(n, dtype=bool); sOB = np.zeros(n, dtype=bool)
    bOBH = np.full(n, np.nan); bOBL = np.full(n, np.nan); bOBMT = np.full(n, np.nan)
    sOBH = np.full(n, np.nan); sOBL = np.full(n, np.nan); sOBMT = np.full(n, np.nan)
    
    o = df_m30["open"].values; h = df_m30["high"].values; l = df_m30["low"].values; c = df_m30["close"].values
    
    # Temporary state
    cbSweep = False; cbSweepBar = -1; cbSweepL = np.nan
    csSweep = False; csSweepBar = -1; csSweepH = np.nan
    cbMSS = False; cbMSSBar = -1; csMSS = False; csMSSBar = -1
    cbFVG = False; cbFVGBar = -1; cbTop = np.nan; cbBot = np.nan
    csFVG = False; csFVGBar = -1; csTop = np.nan; csBot = np.nan
    cbOB = False; cbOBBar = -1; cbOBH = np.nan; cbOBL = np.nan; cbOBMTv = np.nan
    csOB = False; csOBBar = -1; csOBH = np.nan; csOBL = np.nan; csOBMTv = np.nan
    
    for i in range(2, n):
        # Sweeps
        if bull_sweep[i]: cbSweep = True; cbSweepBar = i; cbSweepL = l[i]
        if bear_sweep[i]: csSweep = True; csSweepBar = i; csSweepH = h[i]
        if cbSweep and (i - cbSweepBar) > 20: cbSweep = False
        if csSweep and (i - csSweepBar) > 20: csSweep = False
        bSweepOK[i] = cbSweep; bSweepLow[i] = cbSweepL
        sSweepOK[i] = csSweep; sSweepHigh[i] = csSweepH
        
        # MSS
        if not np.isnan(last_sh[i]) and c[i] > last_sh[i] and c[i-1] <= last_sh[i] and bSweepOK[i]:
            cbMSS = True; cbMSSBar = i
        if not np.isnan(last_sl[i]) and c[i] < last_sl[i] and c[i-1] >= last_sl[i] and sSweepOK[i]:
            csMSS = True; csMSSBar = i
        if cbMSS and (i - cbMSSBar) > 15: cbMSS = False
        if csMSS and (i - csMSSBar) > 15: csMSS = False
        bull_mss[i] = cbMSS; bear_mss[i] = csMSS
        
        # FVG
        if l[i] > h[i-2]: cbFVG = True; cbFVGBar = i; cbTop = l[i]; cbBot = h[i-2]
        if h[i] < l[i-2]: csFVG = True; csFVGBar = i; csTop = l[i-2]; csBot = h[i]
        if cbFVG and (i - cbFVGBar) > 15: cbFVG = False
        if csFVG and (i - csFVGBar) > 15: csFVG = False
        bFVG[i] = cbFVG; bTop[i] = cbTop; bBot[i] = cbBot
        sFVG[i] = csFVG; sTop[i] = csTop; sBot[i] = csBot
        
        # OB
        if c[i] > o[i] and c[i-1] < o[i-1]:
            cbOB = True; cbOBBar = i-1; cbOBH = h[i-1]; cbOBL = l[i-1]; cbOBMTv = (o[i-1]+c[i-1])/2.0
        if c[i] < o[i] and c[i-1] > o[i-1]:
            csOB = True; csOBBar = i-1; csOBH = h[i-1]; csOBL = l[i-1]; csOBMTv = (o[i-1]+c[i-1])/2.0
        if cbOB and (i - cbOBBar) > 15: cbOB = False
        if csOB and (i - csOBBar) > 15: csOB = False
        bOB[i] = cbOB; bOBH[i] = cbOBH; bOBL[i] = cbOBL; bOBMT[i] = cbOBMTv
        sOB[i] = csOB; sOBH[i] = csOBH; sOBL[i] = csOBL; sOBMT[i] = csOBMTv

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
    
    swingEq = (last_sh[-1] + last_sl[-1]) / 2.0 if not (np.isnan(last_sh[-1]) or np.isnan(last_sl[-1])) else np.nan
    i = n - 1
    a14 = atr[i]
    
    # Live Price check (Intrabar Execution)
    current_price = c[i]  # في البوت نستخدم أحدث سعر لحظي هنا

    signals = []
    
    # --- Model 1: IOFED ---
    m1b = sessKZ and (bull_mss[i] or bSweepOK[i]) and bOB[i] and l[i] <= bOBMT[i] and l[i] >= bOBL[i] and c[i] > o[i] and not np.isnan(swingEq) and bOBMT[i] < swingEq and trendUp and (c[i] - o[i]) > a14 * 0.4
    m1s = sessKZ and (bear_mss[i] or sSweepOK[i]) and sOB[i] and h[i] >= sOBMT[i] and h[i] <= sOBH[i] and c[i] < o[i] and not np.isnan(swingEq) and sOBMT[i] > swingEq and trendDown and (o[i] - c[i]) > a14 * 0.4
    if m1b: signals.append({"model": "IOFED", "dir": "BUY", "entry": bOBMT[i], "sl": bOBL[i] - a14*0.3})
    if m1s: signals.append({"model": "IOFED", "dir": "SELL", "entry": sOBMT[i], "sl": sOBH[i] + a14*0.3})

    # --- Model 2: FVG-Direct ---
    bFVG_Age = i - np.where(bFVG)[0][-1] if bFVG.any() else 999
    sFVG_Age = i - np.where(sFVG)[0][-1] if sFVG.any() else 999
    m2b = sessKZ and strongBull and bFVG[i] and bFVG_Age <= 5 and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2 and c[i] > bBot[i] and abs(c[i]-o[i]) > a14*0.3
    m2s = sessKZ and strongBear and sFVG[i] and sFVG_Age <= 5 and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2 and c[i] < sTop[i] and abs(c[i]-o[i]) > a14*0.3
    if m2b: signals.append({"model": "FVG-Direct", "dir": "BUY", "entry": (bTop[i]+bBot[i])/2, "sl": bBot[i] - a14*0.3})
    if m2s: signals.append({"model": "FVG-Direct", "dir": "SELL", "entry": (sTop[i]+sBot[i])/2, "sl": sTop[i] + a14*0.3})

    # --- Model 3: OB-Pro ---
    m3b = sessKZ and strongBull and bOB[i] and (i - cbOBBar) <= 10 and bull_mss[i] and not np.isnan(swingEq) and bOBMT[i] < swingEq and l[i] <= bOBMT[i] and l[i] >= bOBL[i] and c[i] > o[i] and c[i] > bOBMT[i]
    m3s = sessKZ and strongBear and sOB[i] and (i - csOBBar) <= 10 and bear_mss[i] and not np.isnan(swingEq) and sOBMT[i] > swingEq and h[i] >= sOBMT[i] and h[i] <= sOBH[i] and c[i] < o[i] and c[i] < sOBMT[i]
    if m3b: signals.append({"model": "OB-Pro", "dir": "BUY", "entry": bOBMT[i], "sl": bOBL[i] - a14*0.3})
    if m3s: signals.append({"model": "OB-Pro", "dir": "SELL", "entry": sOBMT[i], "sl": sOBH[i] + a14*0.3})
    
    # --- Model 4: SMR ---
    m4b = sessKZ and sSweepOK[i] and bull_mss[i] and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2 and (c[i]-o[i]) > a14*0.5
    m4s = sessKZ and bSweepOK[i] and bear_mss[i] and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2 and (o[i]-c[i]) > a14*0.5
    if m4b: signals.append({"model": "SMR", "dir": "BUY", "entry": (bTop[i]+bBot[i])/2, "sl": bBot[i] - a14*0.3})
    if m4s: signals.append({"model": "SMR", "dir": "SELL", "entry": (sTop[i]+sBot[i])/2, "sl": sTop[i] + a14*0.3})

    # --- Model 9: SBPM-MSS ---
    m9b = sessions["SB-PM"] and bull_mss[i] and bFVG[i] and trendUp
    m9s = sessions["SB-PM"] and bear_mss[i] and sFVG[i] and trendDown
    if m9b: signals.append({"model": "SBPM-MSS", "dir": "BUY", "entry": (bTop[i]+bBot[i])/2, "sl": bSweepLow[i] - a14*0.3})
    if m9s: signals.append({"model": "SBPM-MSS", "dir": "SELL", "entry": (sTop[i]+sBot[i])/2, "sl": sSweepHigh[i] + a14*0.3})

    # --- Model 10: Judas ---
    m10b = sessions["Judas"] and trendUp and bull_sweep[i] and c[i] > o[i]
    m10s = sessions["Judas"] and trendDown and bear_sweep[i] and c[i] < o[i]
    if m10b: signals.append({"model": "Judas", "dir": "BUY", "entry": c[i], "sl": recent_low[i] - a14*0.3})
    if m10s: signals.append({"model": "Judas", "dir": "SELL", "entry": c[i], "sl": recent_high[i] + a14*0.3})

    # --- Model 11: TGIF ---
    m11b = sessions["TGIF"] and trendDown and bull_sweep[i] and c[i] > o[i]
    m11s = sessions["TGIF"] and trendUp and bear_sweep[i] and c[i] < o[i]
    if m11b: signals.append({"model": "TGIF", "dir": "BUY", "entry": c[i], "sl": recent_low[i] - a14*0.3})
    if m11s: signals.append({"model": "TGIF", "dir": "SELL", "entry": c[i], "sl": recent_high[i] + a14*0.3})

    # تصفية الإشارات بناءً على شروط الستوب (40 إلى 130 نقطة)
    valid_signals = []
    for sig in signals:
        risk_pts = abs(sig["entry"] - sig["sl"]) * MULT
        if MIN_SL_PTS <= risk_pts <= MAX_SL_PTS:
            sig["risk_pts"] = risk_pts
            if sig["dir"] == "BUY":
                sig["tp1"] = round(sig["entry"] + TP1_PTS/MULT, 2)
                sig["tp2"] = round(sig["entry"] + TP2_PTS/MULT, 2)
                sig["tp3"] = round(sig["entry"] + TP3_PTS/MULT, 2)
            else:
                sig["tp1"] = round(sig["entry"] - TP1_PTS/MULT, 2)
                sig["tp2"] = round(sig["entry"] - TP2_PTS/MULT, 2)
                sig["tp3"] = round(sig["entry"] - TP3_PTS/MULT, 2)
            valid_signals.append(sig)
            
    return valid_signals

# ==================== إدارة الصفقات (Live) ====================
def manage_active_trades(state, current_price, now_utc):
    if not state.get("active_trades"):
        return
        
    for trade in state["active_trades"][:]:  # نسخة من القائمة للتعديل
        d = trade["direction"]
        e = trade["entry"]
        sl = trade["sl"]
        tp1 = trade["tp1"]
        tp2 = trade["tp2"]
        tp3 = trade["tp3"]
        
        # حساب الوقت المنقضي (للفريم 30 دقيقة، 60 شمعة = 30 ساعة)
        entry_time = datetime.fromisoformat(trade["entry_time"])
        bars_elapsed = (now_utc - entry_time).total_seconds() / 1800 
        
        if bars_elapsed >= MAX_BARS_TRADE:
            trade["current_price"] = current_price
            send_update_msg(trade, "TIME")
            state["active_trades"].remove(trade)
            continue

        # Check Hits
        if d == "BUY":
            if not trade["tp1_hit"] and current_price >= tp1:
                trade["tp1_hit"] = True; trade["sl"] = e
                send_update_msg(trade, "TP1")
            elif trade["tp1_hit"] and not trade["tp2_hit"] and current_price >= tp2:
                trade["tp2_hit"] = True
                send_update_msg(trade, "TP2")
            elif trade["tp2_hit"] and not trade["tp3_hit"] and current_price >= tp3:
                send_update_msg(trade, "TP3")
                state["active_trades"].remove(trade); continue
            elif current_price <= trade["sl"]:
                event = "BE" if trade["tp1_hit"] else "SL"
                send_update_msg(trade, event)
                state["active_trades"].remove(trade); continue
                
        elif d == "SELL":
            if not trade["tp1_hit"] and current_price <= tp1:
                trade["tp1_hit"] = True; trade["sl"] = e
                send_update_msg(trade, "TP1")
            elif trade["tp1_hit"] and not trade["tp2_hit"] and current_price <= tp2:
                trade["tp2_hit"] = True
                send_update_msg(trade, "TP2")
            elif trade["tp2_hit"] and not trade["tp3_hit"] and current_price <= tp3:
                send_update_msg(trade, "TP3")
                state["active_trades"].remove(trade); continue
            elif current_price >= trade["sl"]:
                event = "BE" if trade["tp1_hit"] else "SL"
                send_update_msg(trade, event)
                state["active_trades"].remove(trade); continue

# ==================== المحرك الرئيسي ====================
def main():
    print("Starting ICT Gold v28 Elite Bot...")
    state = {"active_trades": [], "last_day": "", "models_traded_today": []}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, 'r') as f: state = json.load(f)

    now_utc = datetime.now(ZoneInfo("UTC"))
    now_ny = now_utc.astimezone(NY_TZ)
    
    # إعادة ضبط العدادات اليومية
    today = now_ny.date().isoformat()
    if state.get("last_day") != today:
        state["last_day"] = today
        state["models_traded_today"] = []
        
    if now_ny.weekday() >= 5:
        print("Weekend - bot sleeping")
        with open(STATE_FILE, 'w') as f: json.dump(state, f, indent=2)
        return

    account_id = open_session()
    if not account_id:
        print("Failed to open session.")
        return

    df_m30 = fetch_candles(account_id, "M30", 500, 500)
    df_h1 = fetch_candles(account_id, "H1", 500, 500)
    
    if df_m30 is None or df_h1 is None:
        print("Failed to fetch data.")
        return

    # أحدث سعر لحظي
    current_price = float(df_m30.iloc[-1]["close"])

    # 1. إدارة الصفقات المفتوحة أولاً
    manage_active_trades(state, current_price, now_utc)

    # 2. البحث عن صفقات جديدة
    signals = build_and_check_signals(df_m30, df_h1, now_utc, now_ny)
    
    for sig in signals:
        model_name = sig["model"]
        if model_name in state["models_traded_today"]:
            continue # تم التداول بهذا النموذج اليوم
            
        # تسجيل الصفقة
        trade_record = {
            "model": model_name,
            "direction": sig["dir"],
            "entry": round(sig["entry"], 2),
            "sl": round(sig["sl"], 2),
            "tp1": sig["tp1"], "tp2": sig["tp2"], "tp3": sig["tp3"],
            "risk_pts": sig["risk_pts"],
            "entry_time": now_utc.isoformat(),
            "tp1_hit": False, "tp2_hit": False, "tp3_hit": False
        }
        state["active_trades"].append(trade_record)
        state["models_traded_today"].append(model_name)
        send_new_trade_msg(trade_record)
        print(f"New Trade: {model_name} {sig['dir']} @ {sig['entry']}")

    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

if __name__ == "__main__":
    main()