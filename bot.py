import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# ==================== الإعدادات ====================
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TELEGRAM_GROUP_CHAT_ID = os.environ.get("TELEGRAM_GROUP_CHAT_ID")

STATE_FILE = "state.json"
NY_TZ = ZoneInfo("America/New_York")
MOSUL_TZ = ZoneInfo("Asia/Baghdad")

# ==================== الثوابت ====================
MULT = 10.0
ATR_PERIOD = 14
MIN_SL_PTS = 40.0
MAX_SL_PTS = 150.0
COOLDOWN_NORMAL = 10
COOLDOWN_STRONG = 3
MAX_TRADES_PER_DAY = 3
MAX_BARS_TRADE = 60
TP1_R = 1.0
TP2_R = 2.0
TP3_R = 3.0
PIVOT_LEN = 3
SWEEP_LOOKBACK = 20
FVG_EXPIRY = 15
OB_EXPIRY = 15
MSS_EXPIRY = 15
SWEEP_EXPIRY = 20


# ==================== تنسيق الوقت (الموصل، 12 ساعة) ====================
def fmt_mosul(dt_utc):
    """يرجع الوقت بتوقيت الموصل بصيغة 12 ساعة"""
    dt_mosul = dt_utc.astimezone(MOSUL_TZ)
    return dt_mosul.strftime('%I:%M %p')


# ==================== تيليجرام ====================
def send_telegram(message):
    chat_ids = [c for c in [TELEGRAM_CHAT_ID, TELEGRAM_GROUP_CHAT_ID] if c]
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        try:
            r = requests.post(url, json={"chat_id": chat_id, "text": message}, timeout=15)
            print(f"TG->{chat_id}: ok={r.json().get('ok')}")
        except Exception as e:
            print(f"TG Error: {e}")


# ==================== جلب البيانات ====================
def fetch(symbol, interval, outputsize):
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol, "interval": interval,
        "outputsize": outputsize, "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON", "timezone": "UTC"
    }
    r = requests.get(url, params=params, timeout=20)
    data = r.json()
    if "values" not in data:
        print(f"❌ فشل {interval}: {data.get('message')}")
        return None
    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c])
    return df.sort_values("datetime").reset_index(drop=True)


# ==================== المؤشرات ====================
def ta_atr(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0/period, adjust=False).mean()


def ta_ema(series, length):
    return series.ewm(span=length, adjust=False).mean()


def ta_pivothigh(highs, left, right):
    n = len(highs)
    result = np.full(n, np.nan)
    for i in range(left, n - right):
        window = highs[i-left:i+right+1]
        if highs[i] == window.max() and (window == highs[i]).sum() == 1:
            result[i] = highs[i]
    return result


def ta_pivotlow(lows, left, right):
    n = len(lows)
    result = np.full(n, np.nan)
    for i in range(left, n - right):
        window = lows[i-left:i+right+1]
        if lows[i] == window.min() and (window == lows[i]).sum() == 1:
            result[i] = lows[i]
    return result


def ta_lowest(series, length):
    return series.rolling(length).min()


def ta_highest(series, length):
    return series.rolling(length).max()


# ==================== الجلسات ====================
def tm(dt, h1, m1, h2, m2):
    t = dt.hour * 60 + dt.minute
    return (h1 * 60 + m1) <= t < (h2 * 60 + m2)


def session_flags(dt):
    return {
        "SB-LDN":    tm(dt, 3, 0, 4, 0),
        "Judas":     tm(dt, 9, 30, 10, 0),
        "SB-AM":     tm(dt, 10, 0, 11, 0),
        "2022-AM":   tm(dt, 11, 0, 11, 30),
        "Lunch":     tm(dt, 11, 50, 12, 10),
        "SB-PM":     tm(dt, 14, 0, 15, 0),
        "MOC":       tm(dt, 15, 15, 15, 45),
        "FOMC":      tm(dt, 14, 0, 14, 30),
        "TGIF":      (dt.weekday() == 4) and tm(dt, 14, 0, 15, 0),
    }


def is_blackout(dt):
    return tm(dt, 12, 10, 13, 59)


# ==================== الحالة ====================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "active_trade": None,
        "last_entry_time": None,
        "trade_count_today": 0,
        "last_day": None,
        "models_done_today": []
    }


def save_state(s):
    with open(STATE_FILE, "w") as f:
        json.dump(s, f, indent=2)


# ==================== بناء السياق ====================
def build_context(df):
    n = len(df)
    atr = ta_atr(df, ATR_PERIOD).values

    sh = ta_pivothigh(df["high"].values, PIVOT_LEN, PIVOT_LEN)
    sl = ta_pivotlow(df["low"].values, PIVOT_LEN, PIVOT_LEN)

    last_sh = np.full(n, np.nan)
    last_sl = np.full(n, np.nan)
    cur_sh = np.nan
    cur_sl = np.nan
    for i in range(n):
        if not np.isnan(sh[i]): cur_sh = sh[i]
        if not np.isnan(sl[i]): cur_sl = sl[i]
        last_sh[i] = cur_sh
        last_sl[i] = cur_sl

    recent_low = ta_lowest(df["low"], SWEEP_LOOKBACK).shift(1).values
    recent_high = ta_highest(df["high"], SWEEP_LOOKBACK).shift(1).values
    bull_sweep = (df["low"].values < recent_low) & (df["close"].values > recent_low)
    bear_sweep = (df["high"].values > recent_high) & (df["close"].values < recent_high)

    bull_sweep_ok = np.zeros(n, dtype=bool)
    bull_sweep_bar = np.full(n, -1, dtype=int)
    bull_sweep_low = np.full(n, np.nan)
    bear_sweep_ok = np.zeros(n, dtype=bool)
    bear_sweep_bar = np.full(n, -1, dtype=int)
    bear_sweep_high = np.full(n, np.nan)

    cur_bull_ok, cur_bull_bar, cur_bull_low = False, -1, np.nan
    cur_bear_ok, cur_bear_bar, cur_bear_high = False, -1, np.nan

    for i in range(n):
        if bull_sweep[i]:
            cur_bull_ok, cur_bull_bar, cur_bull_low = True, i, df["low"].iloc[i]
        if bear_sweep[i]:
            cur_bear_ok, cur_bear_bar, cur_bear_high = True, i, df["high"].iloc[i]
        if cur_bull_ok and (i - cur_bull_bar) > SWEEP_EXPIRY: cur_bull_ok = False
        if cur_bear_ok and (i - cur_bear_bar) > SWEEP_EXPIRY: cur_bear_ok = False
        bull_sweep_ok[i] = cur_bull_ok
        bull_sweep_bar[i] = cur_bull_bar
        bull_sweep_low[i] = cur_bull_low
        bear_sweep_ok[i] = cur_bear_ok
        bear_sweep_bar[i] = cur_bear_bar
        bear_sweep_high[i] = cur_bear_high

    bull_mss = np.zeros(n, dtype=bool)
    bull_mss_bar = np.full(n, -1, dtype=int)
    bear_mss = np.zeros(n, dtype=bool)
    bear_mss_bar = np.full(n, -1, dtype=int)

    cur_bull_mss, cur_bull_mss_bar = False, -1
    cur_bear_mss, cur_bear_mss_bar = False, -1

    close_arr = df["close"].values
    for i in range(1, n):
        if not np.isnan(last_sh[i]) and close_arr[i] > last_sh[i] and close_arr[i-1] <= last_sh[i] and bull_sweep_ok[i]:
            cur_bull_mss, cur_bull_mss_bar = True, i
        if not np.isnan(last_sl[i]) and close_arr[i] < last_sl[i] and close_arr[i-1] >= last_sl[i] and bear_sweep_ok[i]:
            cur_bear_mss, cur_bear_mss_bar = True, i
        if cur_bull_mss and (i - cur_bull_mss_bar) > MSS_EXPIRY: cur_bull_mss = False
        if cur_bear_mss and (i - cur_bear_mss_bar) > MSS_EXPIRY: cur_bear_mss = False
        bull_mss[i] = cur_bull_mss
        bull_mss_bar[i] = cur_bull_mss_bar
        bear_mss[i] = cur_bear_mss
        bear_mss_bar[i] = cur_bear_mss_bar

    bTop = np.full(n, np.nan); bBot = np.full(n, np.nan)
    bBar = np.full(n, -1, dtype=int); bActive = np.zeros(n, dtype=bool)
    sTop = np.full(n, np.nan); sBot = np.full(n, np.nan)
    sBar = np.full(n, -1, dtype=int); sActive = np.zeros(n, dtype=bool)

    cur_b_top, cur_b_bot, cur_b_bar, cur_b_active = np.nan, np.nan, -1, False
    cur_s_top, cur_s_bot, cur_s_bar, cur_s_active = np.nan, np.nan, -1, False

    low_a = df["low"].values; high_a = df["high"].values
    for i in range(2, n):
        if low_a[i] > high_a[i-2]:
            cur_b_top, cur_b_bot, cur_b_bar, cur_b_active = low_a[i], high_a[i-2], i, True
        if high_a[i] < low_a[i-2]:
            cur_s_top, cur_s_bot, cur_s_bar, cur_s_active = low_a[i-2], high_a[i], i, True
        if cur_b_active and (i - cur_b_bar) > FVG_EXPIRY: cur_b_active = False
        if cur_s_active and (i - cur_s_bar) > FVG_EXPIRY: cur_s_active = False
        bTop[i], bBot[i], bBar[i], bActive[i] = cur_b_top, cur_b_bot, cur_b_bar, cur_b_active
        sTop[i], sBot[i], sBar[i], sActive[i] = cur_s_top, cur_s_bot, cur_s_bar, cur_s_active

    bCE = np.where(bActive, (bTop + bBot) / 2.0, np.nan)
    sCE = np.where(sActive, (sTop + sBot) / 2.0, np.nan)

    bOBHigh = np.full(n, np.nan); bOBLow = np.full(n, np.nan); bOBMT = np.full(n, np.nan)
    bOBBar = np.full(n, -1, dtype=int); bOBActive = np.zeros(n, dtype=bool)
    sOBHigh = np.full(n, np.nan); sOBLow = np.full(n, np.nan); sOBMT = np.full(n, np.nan)
    sOBBar = np.full(n, -1, dtype=int); sOBActive = np.zeros(n, dtype=bool)

    o = df["open"].values; h = df["high"].values; l = df["low"].values; c = df["close"].values

    cur_b_oh, cur_b_ol, cur_b_omt, cur_b_obar, cur_b_oact = np.nan, np.nan, np.nan, -1, False
    cur_s_oh, cur_s_ol, cur_s_omt, cur_s_obar, cur_s_oact = np.nan, np.nan, np.nan, -1, False

    for i in range(1, n):
        if c[i] > o[i] and c[i-1] < o[i-1]:
            cur_b_oh, cur_b_ol = h[i-1], l[i-1]
            cur_b_omt = (o[i-1] + c[i-1]) / 2.0
            cur_b_obar, cur_b_oact = i-1, True
        if c[i] < o[i] and c[i-1] > o[i-1]:
            cur_s_oh, cur_s_ol = h[i-1], l[i-1]
            cur_s_omt = (o[i-1] + c[i-1]) / 2.0
            cur_s_obar, cur_s_oact = i-1, True
        if cur_b_oact and (i - cur_b_obar) > OB_EXPIRY: cur_b_oact = False
        if cur_s_oact and (i - cur_s_obar) > OB_EXPIRY: cur_s_oact = False
        bOBHigh[i], bOBLow[i], bOBMT[i] = cur_b_oh, cur_b_ol, cur_b_omt
        bOBBar[i], bOBActive[i] = cur_b_obar, cur_b_oact
        sOBHigh[i], sOBLow[i], sOBMT[i] = cur_s_oh, cur_s_ol, cur_s_omt
        sOBBar[i], sOBActive[i] = cur_s_obar, cur_s_oact

    bBrkHigh = np.full(n, np.nan); bBrkLow = np.full(n, np.nan)
    bBrkBar = np.full(n, -1, dtype=int); bBrkActive = np.zeros(n, dtype=bool)
    sBrkHigh = np.full(n, np.nan); sBrkLow = np.full(n, np.nan)
    sBrkBar = np.full(n, -1, dtype=int); sBrkActive = np.zeros(n, dtype=bool)

    cur_b_brh, cur_b_brl, cur_b_brbar, cur_b_bract = np.nan, np.nan, -1, False
    cur_s_brh, cur_s_brl, cur_s_brbar, cur_s_bract = np.nan, np.nan, -1, False

    for i in range(n):
        if bull_mss[i] and bull_sweep_ok[i]:
            cur_b_brh, cur_b_brl = last_sh[i], bull_sweep_low[i]
            cur_b_brbar, cur_b_bract = i, True
        if bear_mss[i] and bear_sweep_ok[i]:
            cur_s_brh, cur_s_brl = bear_sweep_high[i], last_sl[i]
            cur_s_brbar, cur_s_bract = i, True
        if cur_b_bract and (i - cur_b_brbar) > 20: cur_b_bract = False
        if cur_s_bract and (i - cur_s_brbar) > 20: cur_s_bract = False
        bBrkHigh[i], bBrkLow[i] = cur_b_brh, cur_b_brl
        bBrkBar[i], bBrkActive[i] = cur_b_brbar, cur_b_bract
        sBrkHigh[i], sBrkLow[i] = cur_s_brh, cur_s_brl
        sBrkBar[i], sBrkActive[i] = cur_s_brbar, cur_s_bract

    bBrkCE = np.where(bBrkActive, (bBrkHigh + bBrkLow) / 2.0, np.nan)
    sBrkCE = np.where(sBrkActive, (sBrkHigh + sBrkLow) / 2.0, np.nan)

    eq_tol = atr * 0.1
    eqHighs = np.zeros(n, dtype=bool)
    eqLows = np.zeros(n, dtype=bool)
    for i in range(n):
        if not np.isnan(last_sh[i]) and not np.isnan(sh[i]):
            if abs(last_sh[i] - sh[i]) < eq_tol[i] and sh[i] != last_sh[i]:
                eqHighs[i] = True
        if not np.isnan(last_sl[i]) and not np.isnan(sl[i]):
            if abs(last_sl[i] - sl[i]) < eq_tol[i] and sl[i] != last_sl[i]:
                eqLows[i] = True

    shallowBull = (low_a < recent_low) & (low_a > (recent_low - 3 * 0.01)) & (c > recent_low)
    shallowBear = (high_a > recent_high) & (high_a < (recent_high + 3 * 0.01)) & (c < recent_high)

    floatUp = (ta_highest(df["high"], 20).values > ta_highest(df["high"], 40).shift(10).values)
    floatDn = (ta_lowest(df["low"], 20).values < ta_lowest(df["low"], 40).shift(10).values)

    bprBull = bActive & sActive & (bBot <= sTop) & (bTop >= sBot)
    bprBear = bActive & sActive & (sBot <= bTop) & (sTop >= bBot)

    rejTouchBull = np.zeros(n, dtype=bool)
    rejTouchBear = np.zeros(n, dtype=bool)
    for i in range(2, n):
        rejBlock = (h[i-1] < h[i-2]) and (c[i-1] > o[i-1])
        if rejBlock and l[i] <= l[i-1] and c[i] > l[i-1]:
            rejTouchBull[i] = True
        rejBlockS = (l[i-1] > l[i-2]) and (c[i-1] < o[i-1])
        if rejBlockS and h[i] >= h[i-1] and c[i] < h[i-1]:
            rejTouchBear[i] = True

    # ==================== إصلاح Liquidity Void ====================
    high_shift2 = np.concatenate([np.full(2, np.nan), high_a[:-2]])
    low_shift2  = np.concatenate([np.full(2, np.nan), low_a[:-2]])

    with np.errstate(invalid='ignore'):
        lqVoidUp = (low_a > high_shift2) & ((low_a - high_shift2) >= atr * 1.5)
        lqVoidDn = (high_a < low_shift2) & ((low_shift2 - high_a) >= atr * 1.5)
    lqVoidUp = np.nan_to_num(lqVoidUp).astype(bool)
    lqVoidDn = np.nan_to_num(lqVoidDn).astype(bool)

    bProp = bOBActive & (c < o) & (h <= bOBHigh) & (l >= bOBLow)
    sProp = sOBActive & (c > o) & (l >= sOBLow) & (h <= sOBHigh)

    mitBull = bBrkActive & (c < o) & (l <= bBrkCE) & (l >= bBrkLow)
    mitBear = sBrkActive & (c > o) & (h >= sBrkCE) & (h <= sBrkHigh)

    asia_high_prev = np.concatenate([[np.nan], h[:-1]])
    asia_low_prev = np.concatenate([[np.nan], l[:-1]])
    p3Bull = (low_a < asia_low_prev) & (c > asia_low_prev) & bull_mss
    p3Bear = (high_a > asia_high_prev) & (c < asia_high_prev) & bear_mss
    p3Bull = np.nan_to_num(p3Bull).astype(bool)
    p3Bear = np.nan_to_num(p3Bear).astype(bool)

    q4 = (df["datetime"].dt.month >= 10).values

    ndogCE = np.full(n, np.nan)
    orgCE = np.full(n, np.nan)
    df_ny = df["datetime"].dt.tz_convert(NY_TZ)
    for i in range(n):
        dt_ny = df_ny.iloc[i]
        if dt_ny.hour == 18 and dt_ny.minute == 0 and i > 0:
            ndogCE[i] = (c[i] + c[i-1]) / 2.0
        elif i > 0 and not np.isnan(ndogCE[i-1]):
            ndogCE[i] = ndogCE[i-1]
        if dt_ny.hour == 9 and dt_ny.minute == 30 and i > 0:
            orgCE[i] = (c[i] + c[i-1]) / 2.0
        elif i > 0 and not np.isnan(orgCE[i-1]):
            orgCE[i] = orgCE[i-1]

    with np.errstate(invalid='ignore'):
        ndogTouchBull = (~np.isnan(ndogCE)) & (low_a <= ndogCE) & (c > ndogCE)
        ndogTouchBear = (~np.isnan(ndogCE)) & (high_a >= ndogCE) & (c < ndogCE)
        orgTouchBull = (~np.isnan(orgCE)) & (low_a <= orgCE) & (c > orgCE)
        orgTouchBear = (~np.isnan(orgCE)) & (high_a >= orgCE) & (c < orgCE)
    ndogTouchBull = np.nan_to_num(ndogTouchBull).astype(bool)
    ndogTouchBear = np.nan_to_num(ndogTouchBear).astype(bool)
    orgTouchBull = np.nan_to_num(orgTouchBull).astype(bool)
    orgTouchBear = np.nan_to_num(orgTouchBear).astype(bool)

    recentBullMSS = bull_mss & ((np.arange(n) - bull_mss_bar) <= 10)
    recentBearMSS = bear_mss & ((np.arange(n) - bear_mss_bar) <= 10)

    return {
        "atr": atr, "last_sh": last_sh, "last_sl": last_sl,
        "bull_sweep_ok": bull_sweep_ok, "bear_sweep_ok": bear_sweep_ok,
        "bull_sweep_low": bull_sweep_low, "bear_sweep_high": bear_sweep_high,
        "bull_mss": bull_mss, "bear_mss": bear_mss,
        "bTop": bTop, "bBot": bBot, "bActive": bActive,
        "sTop": sTop, "sBot": sBot, "sActive": sActive,
        "bCE": bCE, "sCE": sCE,
        "bOBHigh": bOBHigh, "bOBLow": bOBLow, "bOBMT": bOBMT, "bOBActive": bOBActive,
        "sOBHigh": sOBHigh, "sOBLow": sOBLow, "sOBMT": sOBMT, "sOBActive": sOBActive,
        "bBrkActive": bBrkActive, "sBrkActive": sBrkActive,
        "bBrkCE": bBrkCE, "sBrkCE": sBrkCE,
        "bBrkLow": bBrkLow, "sBrkHigh": sBrkHigh,
        "eqHighs": eqHighs, "eqLows": eqLows,
        "shallowBull": shallowBull, "shallowBear": shallowBear,
        "floatUp": floatUp, "floatDn": floatDn,
        "bprBull": bprBull, "bprBear": bprBear,
        "rejTouchBull": rejTouchBull, "rejTouchBear": rejTouchBear,
        "lqVoidUp": lqVoidUp, "lqVoidDn": lqVoidDn,
        "bProp": bProp, "sProp": sProp,
        "mitBull": mitBull, "mitBear": mitBear,
        "p3Bull": p3Bull, "p3Bear": p3Bear,
        "q4": q4,
        "ndogTouchBull": ndogTouchBull, "ndogTouchBear": ndogTouchBear,
        "orgTouchBull": orgTouchBull, "orgTouchBear": orgTouchBear,
        "recentBullMSS": recentBullMSS, "recentBearMSS": recentBearMSS,
    }


# ==================== فحص الإشارة ====================
def check_signal(df5, df1h, state, now_utc, now_ny):
    ctx = build_context(df5)
    i = len(df5) - 1
    atr = ctx["atr"][i]
    if np.isnan(atr): return None

    df1h = df1h.copy()
    df1h["ema200"] = ta_ema(df1h["close"], 200)
    df1h["ema50"] = ta_ema(df1h["close"], 50)
    h1 = df1h.iloc[-2]
    trend_up = h1["close"] > h1["ema200"]
    trend_down = h1["close"] < h1["ema200"]
    strong_bull = trend_up and h1["close"] > h1["ema50"]
    strong_bear = trend_down and h1["close"] < h1["ema50"]

    sessions = session_flags(now_ny)
    active_sessions = [k for k, v in sessions.items() if v]
    if not active_sessions: return None
    if is_blackout(now_ny): return None
    if state["trade_count_today"] >= MAX_TRADES_PER_DAY: return None

    if state["last_entry_time"]:
        last_dt = datetime.fromisoformat(state["last_entry_time"])
        bars_since = int((now_utc - last_dt).total_seconds() / 300)
        cd = COOLDOWN_STRONG if (strong_bull or strong_bear) else COOLDOWN_NORMAL
        if bars_since < cd: return None

    s1L = (ctx["bull_mss"][i] and ctx["bActive"][i] and trend_up)
    s1S = (ctx["bear_mss"][i] and ctx["sActive"][i] and trend_down)

    s17L = ctx["bOBActive"][i] and ctx["bOBLow"][i] <= df5["low"].iloc[i] <= ctx["bOBMT"][i] and trend_up
    s17S = ctx["sOBActive"][i] and ctx["sOBMT"][i] <= df5["high"].iloc[i] <= ctx["sOBHigh"][i] and trend_down

    s18L = ctx["bProp"][i] and ctx["bull_mss"][i] and trend_up
    s18S = ctx["sProp"][i] and ctx["bear_mss"][i] and trend_down

    s20L = ctx["mitBull"][i] and trend_up
    s20S = ctx["mitBear"][i] and trend_down

    s22L = ctx["eqLows"][i] and ctx["bull_sweep_ok"][i] and ctx["bull_mss"][i] and ctx["bActive"][i] and trend_up
    s22S = ctx["eqHighs"][i] and ctx["bear_sweep_ok"][i] and ctx["bear_mss"][i] and ctx["sActive"][i] and trend_down

    s24L = ctx["shallowBull"][i] and ctx["bull_mss"][i] and ctx["bActive"][i] and trend_up
    s24S = ctx["shallowBear"][i] and ctx["bear_mss"][i] and ctx["sActive"][i] and trend_down

    s26L = ctx["floatUp"][i] and ctx["bull_mss"][i] and ctx["bActive"][i] and trend_up
    s26S = ctx["floatDn"][i] and ctx["bear_mss"][i] and ctx["sActive"][i] and trend_down

    s27L = ctx["ndogTouchBull"][i] and ctx["bull_mss"][i] and ctx["bActive"][i] and trend_up
    s27S = ctx["ndogTouchBear"][i] and ctx["bear_mss"][i] and ctx["sActive"][i] and trend_down

    s29L = ctx["orgTouchBull"][i] and ctx["bull_mss"][i] and ctx["bActive"][i] and trend_up
    s29S = ctx["orgTouchBear"][i] and ctx["bear_mss"][i] and ctx["sActive"][i] and trend_down

    s30L = ctx["bprBull"][i] and ctx["bull_mss"][i] and trend_up
    s30S = ctx["bprBear"][i] and ctx["bear_mss"][i] and trend_down

    s32L = ctx["rejTouchBull"][i] and ctx["bull_mss"][i] and ctx["bActive"][i] and trend_up
    s32S = ctx["rejTouchBear"][i] and ctx["bear_mss"][i] and ctx["sActive"][i] and trend_down

    s33L = ctx["lqVoidUp"][i] and ctx["bull_mss"][i] and trend_up
    s33S = ctx["lqVoidDn"][i] and ctx["bear_mss"][i] and trend_down

    s36L = ctx["q4"][i] and ctx["bull_mss"][i] and ctx["bActive"][i] and trend_up
    s36S = ctx["q4"][i] and ctx["bear_mss"][i] and ctx["sActive"][i] and trend_down

    s37L = ctx["p3Bull"][i] and ctx["bActive"][i] and trend_up
    s37S = ctx["p3Bear"][i] and ctx["sActive"][i] and trend_down

    s35L = (now_ny.weekday() == 4) and sessions["TGIF"] and ctx["bull_mss"][i] and ctx["bActive"][i] and trend_up
    s35S = (now_ny.weekday() == 4) and sessions["TGIF"] and ctx["bear_mss"][i] and ctx["sActive"][i] and trend_down

    tcpL = strong_bull and ctx["recentBullMSS"][i] and ctx["bActive"][i] and ctx["bBot"][i] < ctx["bCE"][i] < df5["close"].iloc[i]
    tcpS = strong_bear and ctx["recentBearMSS"][i] and ctx["sActive"][i] and ctx["sTop"][i] > ctx["sCE"][i] > df5["close"].iloc[i]

    fvgL = strong_bull and ctx["bActive"][i] and ctx["bBot"][i] < ctx["bCE"][i] < df5["close"].iloc[i]
    fvgS = strong_bear and ctx["sActive"][i] and ctx["sTop"][i] > ctx["sCE"][i] > df5["close"].iloc[i]

    sigL = s1L or s17L or s18L or s20L or s22L or s24L or s26L or s27L or s29L or s30L or s32L or s33L or s35L or s36L or s37L or tcpL or fvgL
    sigS = s1S or s17S or s18S or s20S or s22S or s24S or s26S or s27S or s29S or s30S or s32S or s33S or s35S or s36S or s37S or tcpS or fvgS

    if not (sigL or sigS): return None

    model = "Unknown"
    if s1L or s1S: model = "SB-LDN/Judas/AM"
    elif s17L or s17S: model = "OB"
    elif s18L or s18S: model = "Prop"
    elif s20L or s20S: model = "Mitig"
    elif s22L or s22S: model = "EQL"
    elif s24L or s24S: model = "Shallow"
    elif s26L or s26S: model = "Float"
    elif s27L or s27S: model = "NDOG"
    elif s29L or s29S: model = "ORG"
    elif s30L or s30S: model = "BPR"
    elif s32L or s32S: model = "Reject"
    elif s33L or s33S: model = "Void"
    elif s35L or s35S: model = "TGIF"
    elif s36L or s36S: model = "Quarter"
    elif s37L or s37S: model = "P3"
    elif tcpL or tcpS: model = "TCP"
    elif fvgL or fvgS: model = "FVG"

    close = df5["close"].iloc[i]
    if sigL:
        if (s17L or s18L) and ctx["bOBActive"][i]:
            entry = ctx["bOBMT"][i]; sl_level = ctx["bOBLow"][i] - atr * 0.3
        elif (fvgL) and ctx["bActive"][i]:
            entry = ctx["bCE"][i]; sl_level = ctx["bBot"][i] - atr * 0.3
        elif ctx["bActive"][i]:
            entry = ctx["bCE"][i]; sl_level = ctx["bull_sweep_low"][i] - atr * 0.3
        else:
            entry = close; sl_level = ctx["bull_sweep_low"][i] - atr * 0.3
        direction = "BUY"
    else:
        if (s17S or s18S) and ctx["sOBActive"][i]:
            entry = ctx["sOBMT"][i]; sl_level = ctx["sOBHigh"][i] + atr * 0.3
        elif (fvgS) and ctx["sActive"][i]:
            entry = ctx["sCE"][i]; sl_level = ctx["sTop"][i] + atr * 0.3
        elif ctx["sActive"][i]:
            entry = ctx["sCE"][i]; sl_level = ctx["bear_sweep_high"][i] + atr * 0.3
        else:
            entry = close; sl_level = ctx["bear_sweep_high"][i] + atr * 0.3
        direction = "SELL"

    if np.isnan(entry) or np.isnan(sl_level): return None

    sl_pts = abs(entry - sl_level) * MULT
    if sl_pts < MIN_SL_PTS or sl_pts > MAX_SL_PTS: return None

    sl_dist = abs(entry - sl_level)
    if direction == "BUY":
        tp1, tp2, tp3 = entry + sl_dist*TP1_R, entry + sl_dist*TP2_R, entry + sl_dist*TP3_R
    else:
        tp1, tp2, tp3 = entry - sl_dist*TP1_R, entry - sl_dist*TP2_R, entry - sl_dist*TP3_R

    return {
        "model": model, "direction": direction,
        "entry": round(entry, 2), "sl": round(sl_level, 2),
        "tp1": round(tp1, 2), "tp2": round(tp2, 2), "tp3": round(tp3, 2)
    }


# ==================== إدارة الصفقة ====================
def manage_trade(state, current_price, now_utc):
    t = state["active_trade"]
    if t is None: return
    d, e, sl, tp1, tp2, tp3 = t["direction"], t["entry"], t["sl"], t["tp1"], t["tp2"], t["tp3"]
    time_str = fmt_mosul(now_utc)

    if (d == "BUY" and current_price <= sl) or (d == "SELL" and current_price >= sl):
        if t["tp1_hit"]:
            send_telegram(f"⚖️ ضرب الستوب بعد TP1 (Break Even)\nالنموذج: {t['model']}\nالاتجاه: {d}\nالدخول: {e}\nالوقت: {time_str}")
        else:
            send_telegram(f"🛑 ضرب الستوب!\nالنموذج: {t['model']}\nالاتجاه: {d}\nالدخول: {e}\nالستوب: {sl}\nالوقت: {time_str}")
        state["active_trade"] = None
        return

    if not t["tp1_hit"] and ((d == "BUY" and current_price >= tp1) or (d == "SELL" and current_price <= tp1)):
        t["tp1_hit"] = True
        send_telegram(f"🎯 ضربنا الهدف الأول! احجز ربحك\nالنموذج: {t['model']}\nالاتجاه: {d}\nTP1: {tp1}\nالوقت: {time_str}")

    if t["tp1_hit"] and not t["tp2_hit"] and ((d == "BUY" and current_price >= tp2) or (d == "SELL" and current_price <= tp2)):
        t["tp2_hit"] = True
        send_telegram(f"🎯🎯 ضربنا الهدف الثاني!\nالنموذج: {t['model']}\nTP2: {tp2}\nالوقت: {time_str}")

    if t["tp2_hit"] and not t["tp3_hit"] and ((d == "BUY" and current_price >= tp3) or (d == "SELL" and current_price <= tp3)):
        t["tp3_hit"] = True
        send_telegram(f"🎯🎯🎯 ضربنا الهدف الثالث! يلا سوي دبچة 🕺🕺🕺\nالنموذج: {t['model']}\nTP3: {tp3}\nالوقت: {time_str}")
        state["active_trade"] = None


# ==================== الدالة الرئيسية ====================
def main():
    print("🤖 بدء...")
    state = load_state()
    now_utc = datetime.now(ZoneInfo("UTC"))
    now_ny = now_utc.astimezone(NY_TZ)

    today = now_ny.date().isoformat()
    if state["last_day"] != today:
        state["trade_count_today"] = 0
        state["models_done_today"] = []
        state["last_day"] = today

    df5 = fetch("XAU/USD", "5min", 500)
    df1h = fetch("XAU/USD", "1h", 500)
    if df5 is None or df1h is None:
        send_telegram("❌ فشل جلب البيانات")
        save_state(state); return

    price = float(df5.iloc[-1]["close"])
    print(f"السعر: {price} | Mosul: {fmt_mosul(now_utc)} | NY: {now_ny.strftime('%H:%M')}")

    if state["active_trade"] is not None:
        manage_trade(state, price, now_utc)
        save_state(state); return

    sig = check_signal(df5, df1h, state, now_utc, now_ny)
    if sig is None:
        print("لا إشارة.")
        save_state(state); return

    state["active_trade"] = {
        **sig,
        "tp1_hit": False, "tp2_hit": False, "tp3_hit": False,
        "entry_time": now_utc.isoformat()
    }
    state["trade_count_today"] += 1
    state["last_entry_time"] = now_utc.isoformat()
    if sig["model"] not in state["models_done_today"]:
        state["models_done_today"].append(sig["model"])

    send_telegram(
        f"🚀 صفقة جديدة!\n\n"
        f"النموذج: {sig['model']}\n"
        f"الاتجاه: {sig['direction']}\n"
        f"الدخول: {sig['entry']}\n"
        f"الستوب: {sig['sl']}\n"
        f"TP1: {sig['tp1']}\n"
        f"TP2: {sig['tp2']}\n"
        f"TP3: {sig['tp3']}\n\n"
        f"الوقت: {fmt_mosul(now_utc)} (الموصل)"
    )
    save_state(state)
    print("✅ إشارة مرسلة")


if __name__ == "__main__":
    main()