import os
import json
import time
import requests
import pandas as pd
import numpy as np
import traceback
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from config import INSTRUMENTS, COOLDOWN_BARS, MAX_BARS_TRADE, EXPIRY_MINUTES, SERVER_OFFSET_HOURS

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

STICKER_NEW_TRADE = "" 
STICKER_TP = ""
STICKER_SL = ""

def fmt_mosul_12h(dt_utc):
    return dt_utc.astimezone(MOSUL_TZ).strftime('%I:%M %p')

# ==================== رسائل التليجرام ====================
def send_telegram_raw(message):
    chat_ids = [c for c in [TELEGRAM_CHAT_ID, TELEGRAM_GROUP_CHAT_ID] if c]
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=15)
        except Exception as e:
            print(f"TG Error: {e}", flush=True)

def send_sticker(sticker_id):
    if not sticker_id: return
    chat_ids = [c for c in [TELEGRAM_CHAT_ID, TELEGRAM_GROUP_CHAT_ID] if c]
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendSticker"
        try:
            requests.post(url, json={"chat_id": chat_id, "sticker": sticker_id}, timeout=15)
        except Exception as e:
            print(f"Sticker Error: {e}", flush=True)

def send_pending_msg(trade, current_price):
    direction_icon = "🟢 <b>BUY LIMIT</b>" if trade["direction"] == "BUY" else "🔴 <b>SELL LIMIT</b>"
    msg = (
        f"⏳ <b>إشارة مبدئية (أمر معلق)</b> ⏳\n\n"
        f"💎 <b>الزوج:</b> {trade['symbol']}\n"
        f"📊 <b>النموذج:</b> {trade['model']}\n"
        f"📈 <b>الاتجاه:</b> {direction_icon}\n"
        f"💰 <b>سعر الدخول (Limit):</b> <code>{trade['entry']}</code>\n"
        f"📉 <b>السعر الحالي:</b> <code>{current_price}</code>\n"
        f"🚫 <b>الستوب:</b> <code>{trade['sl']}</code> (مخاطرة {trade['risk_pts']:.1f} نقطة)\n\n"
        f"🎯 <b>الهدف الأول:</b> <code>{trade['tp1']}</code>\n"
        f"🎯🎯 <b>الهدف الثاني:</b> <code>{trade['tp2']}</code>\n"
        f"🎯🎯🎯 <b>الهدف الثالث:</b> <code>{trade['tp3']}</code>\n\n"
        f"⏰ <b>الوقت:</b> {fmt_mosul_12h(datetime.now(ZoneInfo('UTC')))}\n"
        f"⚠️ <i>سيتم إلغاء الأمر إذا لم يتفعل خلال 60 دقيقة.</i>"
    )
    send_telegram_raw(msg)
    send_sticker(STICKER_NEW_TRADE)

def send_filled_msg(trade):
    direction_icon = "🟢 <b>BUY</b>" if trade["direction"] == "BUY" else "🔴 <b>SELL</b>"
    msg = (
        f"✅ <b>تم تفعيل الصفقة (Market)!</b> ✅\n\n"
        f"💎 <b>الزوج:</b> {trade['symbol']}\n"
        f"📊 <b>النموذج:</b> {trade['model']}\n"
        f"📈 <b>الاتجاه:</b> {direction_icon}\n"
        f"💰 <b>الدخول:</b> <code>{trade['entry']}</code>\n"
        f"🚫 <b>الستوب:</b> <code>{trade['sl']}</code>\n\n"
        f"🎯 <b>الهدف الأول:</b> <code>{trade['tp1']}</code>\n"
        f"🎯🎯 <b>الهدف الثاني:</b> <code>{trade['tp2']}</code>\n"
        f"🎯🎯🎯 <b>الهدف الثالث:</b> <code>{trade['tp3']}</code>\n\n"
        f"⏰ <b>وقت التفعيل:</b> {fmt_mosul_12h(datetime.now(ZoneInfo('UTC')))}\n"
    )
    send_telegram_raw(msg)
    send_sticker(STICKER_NEW_TRADE)

def send_cancelled_msg(trade):
    msg = (
        f"❌ <b>تم إلغاء الأمر المعلق (Expired)</b> ❌\n\n"
        f"💎 <b>الزوج:</b> {trade['symbol']}\n"
        f"📊 <b>النموذج:</b> {trade['model']}\n"
        f"💰 <b>سعر الدخول:</b> <code>{trade['entry']}</code>\n"
        f"⏰ <b>السبب:</b> لم يتم الوصول للسعر خلال ساعة.\n"
    )
    send_telegram_raw(msg)

def send_new_trade_msg(trade):
    direction_icon = "🟢 <b>BUY</b>" if trade["direction"] == "BUY" else "🔴 <b>SELL</b>"
    msg = (
        f"🚀 <b>صفقة فورية (Market)!</b> 🚀\n\n"
        f"💎 <b>الزوج:</b> {trade['symbol']}\n"
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
    sym = trade['symbol']
    now_str = fmt_mosul_12h(datetime.now(ZoneInfo('UTC')))
    
    if event == "TP1":
        msg = f"✅ <b>ضرب الهدف الأول!</b> 🎯\n\n💎 <b>الزوج:</b> {sym}\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>\n🛡️ <b>تم نقل الستوب إلى نقطة الدخول (BE)</b>\n⏰ {now_str}"
        send_sticker(STICKER_TP)
    elif event == "TP2":
        msg = f"✅ <b>ضرب الهدف الثاني!</b> 🎯🎯\n\n💎 <b>الزوج:</b> {sym}\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>\n⏰ {now_str}"
        send_sticker(STICKER_TP)
    elif event == "TP3":
        msg = f"🏆 <b>ضرب الهدف الثالث!</b> 🎯🎯🎯\n\n💎 <b>الزوج:</b> {sym}\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>\n🎉 مبروك الأرباح الكاملة!"
        send_sticker(STICKER_TP)
    elif event == "SL":
        msg = f"❌ <b>ضرب الستوب!</b> 🚫\n\n💎 <b>الزوج:</b> {sym}\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>\n⏰ {now_str}"
        send_sticker(STICKER_SL)
    elif event == "BE":
        msg = f"🛡️ <b>ضرب الستوب بعد الهدف الأول (Break Even)</b>\n\n💎 <b>الزوج:</b> {sym}\n📊 <b>النموذج:</b> {model}\n💰 <b>الدخول:</b> <code>{e}</code>"
        send_sticker(STICKER_SL)
    elif event == "TIME":
        msg = f"⏳ <b>إغلاق الصفقة (Time Exit)</b>\n\n💎 <b>الزوج:</b> {sym}\n📊 <b>النموذج:</b> {model}\n💰 <b>السعر الحالي:</b> <code>{current_price}</code>"
    
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
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            if r.status_code == 200: return r.json().get("accountId")
            else:
                if attempt < max_retries: time.sleep(5)
        except Exception as e:
            if attempt < max_retries: time.sleep(5)
    return None

def fetch_candles(account_id, symbol, timeframe, limit=500, hours=500, divisor=1.0):
    url = BASE_URL + f"/v1/accounts/{account_id}/candles"
    headers = {"Authorization": "Bearer " + TICKERALL_API_KEY}
    params = {"symbol": symbol, "timeframe": timeframe, "limit": limit, "hours": hours}
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
            df[c] = pd.to_numeric(df[c]) / divisor
        return df.sort_values("datetime").reset_index(drop=True)
    except Exception as e:
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
        "Judas": tm(9, 30, 10, 0),
        "SBAM": tm(10, 0, 11, 0),
        "SBPM": tm(14, 0, 15, 0),
        "AMKZ": tm(9, 30, 11, 30),
        "PMKZ": tm(13, 30, 16, 0),
        "FOMC": tm(14, 0, 14, 30),
        "MorningMacro": tm(9, 50, 10, 10),
        "Early": tm(7, 0, 9, 0),
        "anyKZ": tm(9, 30, 11, 30) or tm(13, 30, 16, 0) or tm(10, 0, 11, 0) or tm(14, 0, 15, 0)
    }

# ==================== المنطق الأساسي (المطابق للـ Pine Script v6) ====================
def check_all_models(df_m30, df_h1, now_utc, now_ny, cfg, symbol):
    n = len(df_m30)
    if n < 50: return []
    
    atr = ta_atr(df_m30, 14).values
    atr_sma20 = pd.Series(atr).rolling(20).mean().values
    
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
    
    low50 = df_m30["low"].rolling(50).min().shift(1).values
    high50 = df_m30["high"].rolling(50).max().shift(1).values
    low60 = df_m30["low"].rolling(60).min().shift(1).values
    high60 = df_m30["high"].rolling(60).max().shift(1).values

    bull_sweep = (df_m30["low"].values < recent_low) & (df_m30["close"].values > recent_low)
    bear_sweep = (df_m30["high"].values > recent_high) & (df_m30["close"].values < recent_high)
    
    o = df_m30["open"].values; h = df_m30["high"].values; l = df_m30["low"].values; c = df_m30["close"].values
    bBody = np.abs(c - o)
    bullDisp = (c > o) & (bBody > atr * 0.5)
    bearDisp = (c < o) & (bBody > atr * 0.5)
    
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
    
    cbF = False; cbFBar = -1; cbT = np.nan; cbB = np.nan
    csF = False; csFBar = -1; csT = np.nan; csB = np.nan
    cbO = False; cbOBar = -1; cbOH = np.nan; cbOL = np.nan; cbOMT = np.nan
    csO = False; csOBar = -1; csOH = np.nan; csOL = np.nan; csOMT = np.nan
    cbM_ = False; cbMBar_ = -1; cbMH = np.nan; cbML = np.nan
    csM_ = False; csMBar_ = -1; csMH = np.nan; csML = np.nan
    cbMSS = False; cbMSSBar = -1; csMSS = False; csMSSBar = -1

    for i in range(2, n):
        if not np.isnan(last_sh[i]) and c[i] > last_sh[i] and c[i-1] <= last_sh[i]: cbMSS = True; cbMSSBar = i
        if not np.isnan(last_sl[i]) and c[i] < last_sl[i] and c[i-1] >= last_sl[i]: csMSS = True; csMSSBar = i
        if cbMSS and (i - cbMSSBar) > 15: cbMSS = False
        if csMSS and (i - csMSSBar) > 15: csMSS = False
        bull_mss[i] = cbMSS; bear_mss[i] = csMSS

        if l[i] > h[i-2]: cbF = True; cbFBar = i; cbT = l[i]; cbB = h[i-2]
        if h[i] < l[i-2]: csF = True; csFBar = i; csT = l[i-2]; csB = h[i]
        if cbF and (i - cbFBar) > 10: cbF = False
        if csF and (i - csFBar) > 10: csF = False
        bFVG[i] = cbF; bTop[i] = cbT; bBot[i] = cbB
        sFVG[i] = csF; sTop[i] = csT; sBot[i] = csB
        
        if c[i] > o[i] and c[i-1] < o[i-1]: cbO = True; cbOBar = i-1; cbOH = h[i-1]; cbOL = l[i-1]; cbOMT = (o[i-1]+c[i-1])/2.0
        if c[i] < o[i] and c[i-1] > o[i-1]: csO = True; csOBar = i-1; csOH = h[i-1]; csOL = l[i-1]; csOMT = (o[i-1]+c[i-1])/2.0
        if cbO and (i - cbOBar) > 10: cbO = False
        if csO and (i - csOBar) > 10: csO = False
        bOB[i] = cbO; bOBH[i] = cbOH; bOBL[i] = cbOL; bOBMT[i] = cbOMT
        sOB[i] = csO; sOBH[i] = csOH; sOBL[i] = csOL; sOBMT[i] = csOMT

        if c[i] > o[i] and c[i-1] < o[i-1] and c[i] > h[i-2]: cbM_ = True; cbMBar_ = i-1; cbMH = h[i-1]; cbML = l[i-1]
        if c[i] < o[i] and c[i-1] > o[i-1] and c[i] < l[i-2]: csM_ = True; csMBar_ = i-1; csMH = h[i-1]; csML = l[i-1]
        if cbM_ and (i - cbMBar_) > 10: cbM_ = False
        if csM_ and (i - csMBar_) > 10: csM_ = False
        bMit[i] = cbM_; bMitH[i] = cbMH; bMitL[i] = cbML; bMitCE[i] = (cbMH + cbML)/2
        sMit[i] = csM_; sMitH[i] = csMH; sMitL[i] = csML; sMitCE[i] = (csMH + csML)/2

    df_h1["ema200"] = ta_ema(df_h1["close"], 200)
    h1 = df_h1.iloc[-2]
    trendUp = h1["close"] > h1["ema200"] if not pd.isna(h1["ema200"]) else False
    trendDown = h1["close"] < h1["ema200"] if not pd.isna(h1["ema200"]) else False

    sessions = session_flags(now_ny)
    anyKZ = sessions["anyKZ"]
    
    i = n - 1
    a14 = atr[i]
    a14_sma20 = atr_sma20[i] if not np.isnan(atr_sma20[i]) else a14

    signals = []
    def add_sig(model, dir, entry, sl):
        if model in cfg.get("allowed_models", []):
            signals.append({"model": model, "dir": dir, "entry": entry, "sl": sl})

    # ═══════════ نماذج الذهب GOLD ═══════════
    if cfg["name"] == "GOLD":
        if anyKZ and bFVG[i] and c[i] > bTop[i]: add_sig("M16: Immed Rebal", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and sFVG[i] and c[i] < sBot[i]: add_sig("M16: Immed Rebal", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)
        
        if anyKZ and trendUp and a14 > a14_sma20 and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M53: Risk Gov", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and trendDown and a14 > a14_sma20 and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M53: Risk Gov", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)
        
        if anyKZ and trendUp and bFVG[i] and c[i] > bTop[i]: add_sig("M76: Disrespect BISI", "BUY", bTop[i], bBot[i]-a14*0.3)
        if anyKZ and trendDown and sFVG[i] and c[i] < sBot[i]: add_sig("M76: Disrespect BISI", "SELL", sBot[i], sTop[i]+a14*0.3)
        
        if anyKZ and trendUp and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and l[i-1] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M26: Ma Deuce", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and trendDown and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and h[i-1] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M26: Ma Deuce", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)
        
        if anyKZ and trendUp and bOB[i] and bullDisp[i] and l[i] <= bOBMT[i] and c[i] > bOBMT[i]: add_sig("M6: Propulsion", "BUY", bOBMT[i], bOBL[i]-a14*0.3)
        if anyKZ and trendDown and sOB[i] and bearDisp[i] and h[i] >= sOBMT[i] and c[i] < sOBMT[i]: add_sig("M6: Propulsion", "SELL", sOBMT[i], sOBH[i]+a14*0.3)

        if sessions["MorningMacro"] and trendUp and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M64: Morning Macro", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if sessions["MorningMacro"] and trendDown and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M64: Morning Macro", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)
        
        if anyKZ and trendUp and bear_sweep[i] and (h[i]-c[i]) > (c[i]-o[i])*2 and c[i] > o[i]: add_sig("M18: Rejection", "BUY", c[i], l[i]-a14*0.3)
        if anyKZ and trendDown and bull_sweep[i] and (c[i]-l[i]) > (o[i]-c[i])*2 and c[i] < o[i]: add_sig("M18: Rejection", "SELL", c[i], h[i]+a14*0.3)

        if anyKZ and trendUp and bOB[i] and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M11: Unicorn", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and trendDown and sOB[i] and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M11: Unicorn", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)
        
        if anyKZ and trendUp and bMit[i] and l[i] <= bMitCE[i] and c[i] > bMitCE[i]: add_sig("M17: Mitigation", "BUY", bMitCE[i], bMitL[i]-a14*0.3)
        if anyKZ and trendDown and sMit[i] and h[i] >= sMitCE[i] and c[i] < sMitCE[i]: add_sig("M17: Mitigation", "SELL", sMitCE[i], sMitH[i]+a14*0.3)
        
        if sessions["AMKZ"] and trendUp and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M45: 10-Min Rule", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if sessions["AMKZ"] and trendDown and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M45: 10-Min Rule", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

        if (sessions["SBAM"] or sessions["SBPM"]) and trendUp and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M54: Algo Clock", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if (sessions["SBAM"] or sessions["SBPM"]) and trendDown and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M54: Algo Clock", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

        if anyKZ and trendUp and bull_mss[i] and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M50: Key Turn Pt", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and trendDown and bear_mss[i] and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M50: Key Turn Pt", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)
        
        if anyKZ and trendUp and bFVG[i] and bOB[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2 and bull_mss[i]: add_sig("M106: BPR Bolo", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and trendDown and sFVG[i] and sOB[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2 and bear_mss[i]: add_sig("M106: BPR Bolo", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

    # ═══════════ نماذج الناسداك NAS100 ═══════════
    elif cfg["name"] == "NAS100":
        if anyKZ and trendUp and bull_sweep[i] and bull_mss[i] and bullDisp[i] and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M1: ICT 2022", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and trendDown and bear_sweep[i] and bear_mss[i] and bearDisp[i] and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M4: MMSM", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)
        
        if sessions["FOMC"] and trendUp and bullDisp[i] and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M13: FOMC 2-Stage", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if sessions["FOMC"] and trendDown and bearDisp[i] and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M13: FOMC 2-Stage", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

        if anyKZ and bFVG[i] and c[i] > bTop[i]: add_sig("M16: Immed Rebal", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and sFVG[i] and c[i] < sBot[i]: add_sig("M16: Immed Rebal", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

        if anyKZ and trendUp and bMit[i] and l[i] <= bMitCE[i] and c[i] > bMitCE[i]: add_sig("M17: Mitigation", "BUY", bMitCE[i], bMitL[i]-a14*0.3)
        if anyKZ and trendDown and sMit[i] and h[i] >= sMitCE[i] and c[i] < sMitCE[i]: add_sig("M17: Mitigation", "SELL", sMitCE[i], sMitH[i]+a14*0.3)

        if anyKZ and trendUp and l[i] < low50[i] and c[i] > o[i]: add_sig("M41: Old Highs", "BUY", c[i], low50[i]-a14*0.3)
        if anyKZ and trendDown and h[i] > high50[i] and c[i] < o[i]: add_sig("M41: Old Highs", "SELL", c[i], high50[i]+a14*0.3)

        if sessions["AMKZ"] and trendUp and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M64: Morning Macro", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if sessions["AMKZ"] and trendDown and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M64: Morning Macro", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

        if anyKZ and trendUp and l[i] < low60[i] and c[i] > o[i]: add_sig("M92: Real Void", "BUY", c[i], low60[i]-a14*0.3)
        if anyKZ and trendDown and h[i] > high60[i] and c[i] < o[i]: add_sig("M92: Real Void", "SELL", c[i], high60[i]+a14*0.3)

        if anyKZ and trendUp and bBody[i] > a14*1.5 and c[i] > o[i]: add_sig("M102: Full Replic", "BUY", c[i], l[i]-a14*0.3)
        if anyKZ and trendDown and bBody[i] > a14*1.5 and c[i] < o[i]: add_sig("M102: Full Replic", "SELL", c[i], h[i]+a14*0.3)

    # ═══════════ نماذج الداو جونز US30 ═══════════
    elif cfg["name"] == "US30":
        if anyKZ and trendUp and bOB[i] and bullDisp[i] and l[i] <= bOBMT[i] and c[i] > bOBMT[i]: add_sig("M6: Propulsion", "BUY", bOBMT[i], bOBL[i]-a14*0.3)
        if anyKZ and trendDown and sOB[i] and bearDisp[i] and h[i] >= sOBMT[i] and c[i] < sOBMT[i]: add_sig("M6: Propulsion", "SELL", sOBMT[i], sOBH[i]+a14*0.3)

        if anyKZ and trendUp and bOB[i] and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M11: Unicorn", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and trendDown and sOB[i] and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M11: Unicorn", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

        if anyKZ and bFVG[i] and c[i] > bTop[i]: add_sig("M16: Immed Rebal", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and sFVG[i] and c[i] < sBot[i]: add_sig("M16: Immed Rebal", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

        if anyKZ and trendUp and bMit[i] and l[i] <= bMitCE[i] and c[i] > bMitCE[i]: add_sig("M17: Mitigation", "BUY", bMitCE[i], bMitL[i]-a14*0.3)
        if anyKZ and trendDown and sMit[i] and h[i] >= sMitCE[i] and c[i] < sMitCE[i]: add_sig("M17: Mitigation", "SELL", sMitCE[i], sMitH[i]+a14*0.3)

        if sessions["AMKZ"] and trendUp and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M45: 10-Min Rule", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if sessions["AMKZ"] and trendDown and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M45: 10-Min Rule", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

        if sessions["MorningMacro"] and trendUp and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M64: Morning Macro", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if sessions["MorningMacro"] and trendDown and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M64: Morning Macro", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

        if sessions["Early"] and trendUp and bull_sweep[i] and bullDisp[i]: add_sig("M104: Early Focus", "BUY", c[i], l[i]-a14*0.3)
        if sessions["Early"] and trendDown and bear_sweep[i] and bearDisp[i]: add_sig("M104: Early Focus", "SELL", c[i], h[i]+a14*0.3)

    # ═══════════ نماذج الباوند ين GBPJPY ═══════════
    elif cfg["name"] == "GBPJPY":
        if anyKZ and trendUp and bOB[i] and bullDisp[i] and l[i] <= bOBMT[i] and c[i] > bOBMT[i]: add_sig("M6: Propulsion", "BUY", bOBMT[i], bOBL[i]-a14*0.3)
        if anyKZ and trendDown and sOB[i] and bearDisp[i] and h[i] >= sOBMT[i] and c[i] < sOBMT[i]: add_sig("M6: Propulsion", "SELL", sOBMT[i], sOBH[i]+a14*0.3)

        if sessions["Judas"] and trendUp and bull_sweep[i] and c[i] > o[i]: add_sig("M10: Judas Swing", "BUY", c[i], recent_low[i]-a14*0.3)
        if sessions["Judas"] and trendDown and bear_sweep[i] and c[i] < o[i]: add_sig("M10: Judas Swing", "SELL", c[i], recent_high[i]+a14*0.3)

        if sessions["FOMC"] and trendUp and bullDisp[i] and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M13: FOMC 2-Stage", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if sessions["FOMC"] and trendDown and bearDisp[i] and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M13: FOMC 2-Stage", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

        if anyKZ and bFVG[i] and c[i] > bTop[i]: add_sig("M16: Immed Rebal", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and sFVG[i] and c[i] < sBot[i]: add_sig("M16: Immed Rebal", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

        if sessions["AMKZ"] and trendUp and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M45: 10-Min Rule", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if sessions["AMKZ"] and trendDown and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M45: 10-Min Rule", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

    # ═══════════ نماذج اليورو دولار EURUSD ═══════════
    elif cfg["name"] == "EURUSD":
        if (sessions["SBAM"] or sessions["SBPM"]) and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M2: Silver Bullet", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if (sessions["SBAM"] or sessions["SBPM"]) and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M2: Silver Bullet", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)
        if anyKZ and bFVG[i] and c[i] > bTop[i]: add_sig("M16: Immed Rebal", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and sFVG[i] and c[i] < sBot[i]: add_sig("M16: Immed Rebal", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

    # ═══════════ نماذج الدولار فرنك USDCHF ═══════════
    elif cfg["name"] == "USDCHF":
        if anyKZ and bFVG[i] and c[i] > bTop[i]: add_sig("M16: Immed Rebal", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and sFVG[i] and c[i] < sBot[i]: add_sig("M16: Immed Rebal", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)
        if anyKZ and trendUp and (h[i]-l[i]) < a14*0.5 and bull_sweep[i]: add_sig("M31: Seek/Destroy", "BUY", c[i], recent_low[i]-a14*0.3)
        if anyKZ and trendDown and (h[i]-l[i]) < a14*0.5 and bear_sweep[i]: add_sig("M31: Seek/Destroy", "SELL", c[i], recent_high[i]+a14*0.3)

    # ═══════════ نماذج الباوند دولار GBPUSD ═══════════
    elif cfg["name"] == "GBPUSD":
        if anyKZ and bFVG[i] and c[i] > bTop[i]: add_sig("M16: Immed Rebal", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and sFVG[i] and c[i] < sBot[i]: add_sig("M16: Immed Rebal", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)
        
        isQShift = now_ny.day <= 5
        if isQShift and anyKZ and trendUp and bull_sweep[i] and bullDisp[i]: add_sig("M42: Q-Shift", "BUY", c[i], recent_low[i]-a14*0.3)
        if isQShift and anyKZ and trendDown and bear_sweep[i] and bearDisp[i]: add_sig("M42: Q-Shift", "SELL", c[i], recent_high[i]+a14*0.3)

    # ═══════════ نماذج اليورو ين EURJPY ═══════════
    elif cfg["name"] == "EURJPY":
        if anyKZ and bFVG[i] and c[i] > bTop[i]: add_sig("M16: Immed Rebal", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if anyKZ and sFVG[i] and c[i] < sBot[i]: add_sig("M16: Immed Rebal", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)
        
        if anyKZ and trendUp and c[i] > o[i] and bBody[i] > a14: add_sig("M43: Anti-Revenge", "BUY", c[i], l[i]-a14*0.3)
        if anyKZ and trendDown and c[i] < o[i] and bBody[i] > a14: add_sig("M43: Anti-Revenge", "SELL", c[i], h[i]+a14*0.3)

        if sessions["FOMC"] and trendUp and bullDisp[i] and bFVG[i] and l[i] <= (bTop[i]+bBot[i])/2 and c[i] > (bTop[i]+bBot[i])/2: add_sig("M13: FOMC 2-Stage", "BUY", (bTop[i]+bBot[i])/2, bBot[i]-a14*0.3)
        if sessions["FOMC"] and trendDown and bearDisp[i] and sFVG[i] and h[i] >= (sTop[i]+sBot[i])/2 and c[i] < (sTop[i]+sBot[i])/2: add_sig("M13: FOMC 2-Stage", "SELL", (sTop[i]+sBot[i])/2, sTop[i]+a14*0.3)

        if anyKZ and trendUp and bull_sweep[i] and bullDisp[i]: add_sig("M32: Sympathy", "BUY", c[i], recent_low[i]-a14*0.3)
        if anyKZ and trendDown and bear_sweep[i] and bearDisp[i]: add_sig("M32: Sympathy", "SELL", c[i], recent_high[i]+a14*0.3)

    # تصفية الإشارات وحساب الأهداف
    valid_signals = []
    for sig in signals:
        mult = cfg["mult"]
        digits = cfg["digits"]
        risk = abs(sig["entry"] - sig["sl"]) * mult
        
        if cfg["min_sl"] <= risk <= cfg["max_sl"]:
            tp1_pts, tp2_pts, tp3_pts = cfg["tp"]
            
            if sig["dir"] == "BUY":
                sig["tp1"] = round(sig["entry"] + tp1_pts/mult, digits)
                sig["tp2"] = round(sig["entry"] + tp2_pts/mult, digits)
                sig["tp3"] = round(sig["entry"] + tp3_pts/mult, digits)
            else:
                sig["tp1"] = round(sig["entry"] - tp1_pts/mult, digits)
                sig["tp2"] = round(sig["entry"] - tp2_pts/mult, digits)
                sig["tp3"] = round(sig["entry"] - tp3_pts/mult, digits)
            sig["risk_pts"] = risk
            valid_signals.append(sig)
            
    return valid_signals

# ==================== إدارة الصفقات ====================
def manage_active_trades(state, symbol, current_price, now_utc):
    if "active_trades" not in state: state["active_trades"] = []
    for trade in state["active_trades"][:]:
        if trade.get("symbol") != symbol: continue
        
        d = trade["direction"]; e = trade["entry"]
        tp1 = trade["tp1"]; tp2 = trade["tp2"]; tp3 = trade["tp3"]
        
        entry_time = datetime.fromisoformat(trade["entry_time"])
        bars_elapsed = (now_utc - entry_time).total_seconds() / 1800 
        
        if bars_elapsed >= MAX_BARS_TRADE:
            send_update_msg(trade, "TIME", current_price)
            state["active_trades"].remove(trade)
            continue

        if d == "BUY":
            if not trade["tp1_hit"] and current_price >= tp1:
                trade["tp1_hit"] = True; trade["sl"] = e; send_update_msg(trade, "TP1")
            if trade["tp1_hit"] and not trade["tp2_hit"] and current_price >= tp2:
                trade["tp2_hit"] = True; send_update_msg(trade, "TP2")
            if trade["tp2_hit"] and not trade["tp3_hit"] and current_price >= tp3:
                send_update_msg(trade, "TP3"); state["active_trades"].remove(trade); continue
            if current_price <= trade["sl"]:
                event = "BE" if trade["tp1_hit"] else "SL"
                send_update_msg(trade, event); state["active_trades"].remove(trade); continue
                
        elif d == "SELL":
            if not trade["tp1_hit"] and current_price <= tp1:
                trade["tp1_hit"] = True; trade["sl"] = e; send_update_msg(trade, "TP1")
            if trade["tp1_hit"] and not trade["tp2_hit"] and current_price <= tp2:
                trade["tp2_hit"] = True; send_update_msg(trade, "TP2")
            if trade["tp2_hit"] and not trade["tp3_hit"] and current_price <= tp3:
                send_update_msg(trade, "TP3"); state["active_trades"].remove(trade); continue
            if current_price >= trade["sl"]:
                event = "BE" if trade["tp1_hit"] else "SL"
                send_update_msg(trade, event); state["active_trades"].remove(trade); continue

# ==================== المحرك الرئيسي ====================
def main():
    print("Starting ICT Ultimate Multi-Symbol Bot (v6)...", flush=True)
    state = {"active_trades": [], "pending_orders": [], "last_day": "", "last_entry_times": {}}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f: 
                loaded = json.load(f)
                if "active_trades" not in loaded: loaded["active_trades"] = []
                if "pending_orders" not in loaded: loaded["pending_orders"] = []
                if "last_entry_times" not in loaded: loaded["last_entry_times"] = {}
                state = loaded
        except Exception: pass

    now_utc = datetime.now(ZoneInfo("UTC"))
    now_ny = now_utc.astimezone(NY_TZ)
    
    today = now_ny.date().isoformat()
    if state.get("last_day") != today:
        state["last_day"] = today
        state["last_entry_times"] = {}
        
    if now_ny.weekday() >= 5:
        print("Weekend - sleeping", flush=True)
        with open(STATE_FILE, 'w') as f: json.dump(state, f, indent=2)
        return

    account_id = open_session()
    if not account_id: return

    for symbol, cfg in INSTRUMENTS.items():
        print(f"\n--- Checking {symbol} ---", flush=True)
        
        div = cfg.get("divisor", 1.0)
        df_m30 = fetch_candles(account_id, symbol, "M30", 500, 500, divisor=div)
        df_h1 = fetch_candles(account_id, symbol, "H1", 500, 500, divisor=div)
        
        if df_m30 is None or df_h1 is None:
            print(f"Failed to fetch data for {symbol}", flush=True)
            continue

        # 👈 تم إضافة التدوير هنا لمنع الكسور الطويلة
        current_price = round(float(df_m30.iloc[-1]["close"]), cfg.get("digits", 2))
        print(f"Current Price: {current_price} | Time: {fmt_mosul_12h(now_utc)}", flush=True)

        # 1. إدارة الصفقات النشطة
        manage_active_trades(state, symbol, current_price, now_utc)

        # 2. إدارة الأوامر المعلقة
        for order in state["pending_orders"][:]:
            if order.get("symbol") != symbol: continue 
            
            created_at = datetime.fromisoformat(order["created_at"])
            time_elapsed = (now_utc - created_at).total_seconds()
            
            if time_elapsed > (EXPIRY_MINUTES * 60):
                print(f"Cancelled (Expired): {order['model']} on {symbol}", flush=True)
                state["pending_orders"].remove(order)
                send_cancelled_msg(order)
                continue
                
            is_filled = False
            if order["direction"] == "BUY" and current_price <= order["entry"]: is_filled = True
            elif order["direction"] == "SELL" and current_price >= order["entry"]: is_filled = True
                
            if is_filled:
                print(f"Filled: {order['model']} on {symbol}", flush=True)
                state["pending_orders"].remove(order)
                order["entry_time"] = now_utc.isoformat()
                state["active_trades"].append(order)
                state["last_entry_times"][f"{symbol}_{order['model']}"] = now_utc.isoformat()
                send_filled_msg(order)

        # 3. فحص إشارات جديدة
        signals = check_all_models(df_m30, df_h1, now_utc, now_ny, cfg, symbol)
        print(f"Signals found: {len(signals)}", flush=True)
        
        for sig in signals:
            model_name = sig["model"]
            
            last_entry = state.get("last_entry_times", {}).get(f"{symbol}_{model_name}")
            if last_entry:
                last_dt = datetime.fromisoformat(last_entry)
                if (now_utc - last_dt).total_seconds() / 1800 < COOLDOWN_BARS: continue

            if any(t["model"] == model_name and t.get("symbol") == symbol for t in state["active_trades"]): continue
            if any(t["model"] == model_name and t.get("symbol") == symbol for t in state["pending_orders"]): continue

            dist_pts = abs(sig["entry"] - current_price) * cfg["mult"]
            
            if dist_pts > cfg["max_dist"]:
                print(f"⏭️ Ignored {model_name} on {symbol}: Entry is too far ({dist_pts:.1f} pts, max {cfg['max_dist']})", flush=True)
                continue

            trade_record = {
                "symbol": symbol,
                "model": model_name, "direction": sig["dir"],
                "entry": round(sig["entry"], cfg["digits"]), 
                "sl": round(sig["sl"], cfg["digits"]),
                "tp1": sig["tp1"], "tp2": sig["tp2"], "tp3": sig["tp3"],
                "risk_pts": sig["risk_pts"],
                "tp1_hit": False, "tp2_hit": False, "tp3_hit": False
            }

            is_market = False
            if sig["dir"] == "BUY" and current_price <= sig["entry"]: is_market = True
            elif sig["dir"] == "SELL" and current_price >= sig["entry"]: is_market = True

            if is_market:
                trade_record["entry_time"] = now_utc.isoformat()
                state["active_trades"].append(trade_record)
                state["last_entry_times"][f"{symbol}_{model_name}"] = now_utc.isoformat()
                send_new_trade_msg(trade_record)
                print(f"✅ Market Trade: {model_name} on {symbol}", flush=True)
            else:
                trade_record["created_at"] = now_utc.isoformat()
                state["pending_orders"].append(trade_record)
                send_pending_msg(trade_record, current_price)
                print(f"⏳ Pending Order on {symbol} (Close by {dist_pts:.1f} pts): {model_name}", flush=True)

    with open(STATE_FILE, 'w') as f:
        json.dump(state, f, indent=2)

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"FATAL ERROR: {e}", flush=True)
        traceback.print_exc()