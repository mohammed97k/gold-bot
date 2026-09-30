import os
import json
import requests
import pandas as pd
import numpy as np
from datetime import datetime
from zoneinfo import ZoneInfo

# ==================== الإعدادات ====================
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
TELEGRAM_GROUP_CHAT_ID = os.environ.get("TELEGRAM_GROUP_CHAT_ID")
GITHUB_REPO = os.environ.get("GITHUB_REPOSITORY", "")  # مدمج تلقائياً في GitHub Actions

STATE_FILE = "state.json"
NY_TZ = ZoneInfo("America/New_York")

# ==================== إعدادات الاستراتيجية ====================
MULT = 10.0
ATR_PERIOD = 14
MIN_SL_PTS = 40.0
MAX_SL_PTS = 150.0
TP1_R = 1.0
TP2_R = 2.0
TP3_R = 3.0
MAX_TRADES_PER_DAY = 3
COOLDOWN_NORMAL = 10
COOLDOWN_STRONG = 3
MAX_BARS_TRADE = 60


# ==================== تيليجرام ====================
def send_telegram(message):
    chat_ids = []
    if TELEGRAM_CHAT_ID:
        chat_ids.append(TELEGRAM_CHAT_ID)
    if TELEGRAM_GROUP_CHAT_ID:
        chat_ids.append(TELEGRAM_GROUP_CHAT_ID)
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": chat_id, "text": message}
        try:
            r = requests.post(url, json=payload, timeout=15)
            print(f"Telegram -> {chat_id}: {r.json().get('ok')}")
        except Exception as e:
            print(f"Telegram Error: {e}")


# ==================== جلب البيانات ====================
def fetch_ohlc(interval="5min", outputsize=500, symbol="XAU/USD"):
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": interval,
        "outputsize": outputsize,
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON",
        "timezone": "UTC"
    }
    r = requests.get(url, params=params, timeout=20)
    data = r.json()
    if "values" not in data:
        print(f"❌ فشل جلب {interval}: {data.get('message', 'unknown')}")
        return None
    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
    for c in ["open", "high", "low", "close"]:
        df[c] = pd.to_numeric(df[c])
    df = df.sort_values("datetime").reset_index(drop=True)
    return df


# ==================== المؤشرات ====================
def calc_atr(df, period=14):
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs()
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1/period, adjust=False).mean()


def calc_ema(series, span):
    return series.ewm(span=span, adjust=False).mean()


def calc_pivots(df, left=3, right=3):
    highs = df["high"].values
    lows = df["low"].values
    n = len(df)
    pivot_high = [np.nan] * n
    pivot_low = [np.nan] * n
    for i in range(left, n - right):
        window_h = highs[i-left:i+right+1]
        window_l = lows[i-left:i+right+1]
        if highs[i] == window_h.max():
            pivot_high[i] = highs[i]
        if lows[i] == window_l.min():
            pivot_low[i] = lows[i]
    return pivot_high, pivot_low


# ==================== فلتر الجلسات (توقيت نيويورك) ====================
def in_session(dt_ny, start_h, start_m, end_h, end_m):
    t = dt_ny.hour * 60 + dt_ny.minute
    s = start_h * 60 + start_m
    e = end_h * 60 + end_m
    return s <= t < e


def get_active_sessions(dt_ny):
    """يرجع قائمة الجلسات النشطة في هذا الوقت"""
    sessions = []
    if in_session(dt_ny, 3, 0, 4, 0):    sessions.append("SB-LDN")
    if in_session(dt_ny, 9, 30, 10, 0):  sessions.append("Judas")
    if in_session(dt_ny, 10, 0, 11, 0):  sessions.append("SB-AM")
    if in_session(dt_ny, 11, 0, 11, 30): sessions.append("2022-AM")
    if in_session(dt_ny, 11, 50, 12, 10): sessions.append("Lunch")
    if in_session(dt_ny, 14, 0, 15, 0):  sessions.append("SB-PM")
    if in_session(dt_ny, 15, 15, 15, 45): sessions.append("MOC")
    if in_session(dt_ny, 14, 0, 14, 30): sessions.append("FOMC")
    if dt_ny.weekday() == 4 and in_session(dt_ny, 14, 0, 15, 0):
        sessions.append("TGIF")
    return sessions


def in_blackout(dt_ny):
    return in_session(dt_ny, 12, 10, 13, 59)


# ==================== حفظ/تحميل الحالة ====================
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "active_trade": None,
        "last_entry_time": None,
        "trade_count_today": 0,
        "last_day": None,
        "models_done_today": []
    }


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


# ==================== إدارة الصفقة ====================
def check_active_trade(state, current_price, current_time):
    trade = state["active_trade"]
    if trade is None:
        return
    direction = trade["direction"]
    entry = trade["entry"]
    sl = trade["sl"]
    tp1 = trade["tp1"]
    tp2 = trade["tp2"]
    tp3 = trade["tp3"]

    # فحص الستوب
    if (direction == "BUY" and current_price <= sl) or \
       (direction == "SELL" and current_price >= sl):
        if not trade["tp1_hit"]:
            send_telegram(
                f"🛑 ضرب الستوب!\n"
                f"النموذج: {trade['model']}\n"
                f"الاتجاه: {direction}\n"
                f"الدخول: {entry}\n"
                f"الستوب: {sl}\n"
                f"الوقت: {current_time.strftime('%H:%M')}"
            )
        else:
            send_telegram(
                f"⚖️ ضرب الستوب بعد TP1 (Break Even)\n"
                f"النموذج: {trade['model']}\n"
                f"الاتجاه: {direction}\n"
                f"الدخول: {entry}\n"
                f"الوقت: {current_time.strftime('%H:%M')}"
            )
        state["active_trade"] = None
        return

    # فحص الأهداف
    if not trade["tp1_hit"]:
        if (direction == "BUY" and current_price >= tp1) or \
           (direction == "SELL" and current_price <= tp1):
            trade["tp1_hit"] = True
            send_telegram(
                f"🎯 ضربنا الهدف الأول! احجز ربحك\n"
                f"النموذج: {trade['model']}\n"
                f"الاتجاه: {direction}\n"
                f"TP1: {tp1}\n"
                f"الوقت: {current_time.strftime('%H:%M')}"
            )

    if trade["tp1_hit"] and not trade["tp2_hit"]:
        if (direction == "BUY" and current_price >= tp2) or \
           (direction == "SELL" and current_price <= tp2):
            trade["tp2_hit"] = True
            send_telegram(
                f"🎯🎯 ضربنا الهدف الثاني!\n"
                f"النموذج: {trade['model']}\n"
                f"الاتجاه: {direction}\n"
                f"TP2: {tp2}\n"
                f"الوقت: {current_time.strftime('%H:%M')}"
            )

    if trade["tp2_hit"] and not trade["tp3_hit"]:
        if (direction == "BUY" and current_price >= tp3) or \
           (direction == "SELL" and current_price <= tp3):
            trade["tp3_hit"] = True
            send_telegram(
                f"🎯🎯🎯 ضربنا الهدف الثالث! يلا سوي دبچة 🕺🕺🕺\n"
                f"النموذج: {trade['model']}\n"
                f"الاتجاه: {direction}\n"
                f"TP3: {tp3}\n"
                f"الوقت: {current_time.strftime('%H:%M')}"
            )
            state["active_trade"] = None


# ==================== فحص الإشارات ====================
def detect_signals(df5, df1h, state, current_time):
    """يرجع قائمة بالصفقات المقترحة"""
    signals = []

    # حساب المؤشرات على 5 دقائق
    df5["atr"] = calc_atr(df5, ATR_PERIOD)
    last = df5.iloc[-1]
    atr = last["atr"]
    if pd.isna(atr):
        return signals

    # حساب الترند على H1
    df1h["ema200"] = calc_ema(df1h["close"], 200)
    df1h["ema50"] = calc_ema(df1h["close"], 50)
    h1_last = df1h.iloc[-1]
    trend_up = h1_last["close"] > h1_last["ema200"]
    trend_down = h1_last["close"] < h1_last["ema200"]
    strong_bull = trend_up and h1_last["close"] > h1_last["ema50"]
    strong_bear = trend_down and h1_last["close"] < h1_last["ema50"]

    # Pivots (نحسب على آخر 100 شمعة لتسريع الحساب)
    df_recent = df5.tail(200).reset_index(drop=True)
    ph, pl = calc_pivots(df_recent, 3, 3)

    # آخر swing high / low
    last_sh = None
    last_sl = None
    for i in range(len(df_recent) - 1, -1, -1):
        if last_sh is None and not np.isnan(ph[i]):
            last_sh = ph[i]
        if last_sl is None and not np.isnan(pl[i]):
            last_sl = pl[i]
        if last_sh is not None and last_sl is not None:
            break

    if last_sh is None or last_sl is None:
        return signals

    # Sweep - استخدام آخر 20 شمعة
    recent_low_20 = df_recent["low"].iloc[-21:-1].min()
    recent_high_20 = df_recent["high"].iloc[-21:-1].max()

    bull_sweep = (last["low"] < recent_low_20) and (last["close"] > recent_low_20)
    bear_sweep = (last["high"] > recent_high_20) and (last["close"] < recent_high_20)

    # MSS: كسر آخر swing high/low
    bull_mss = False
    bear_mss = False
    if len(df_recent) >= 2:
        prev = df_recent.iloc[-2]
        if last["close"] > last_sh and prev["close"] <= last_sh and bull_sweep:
            bull_mss = True
        if last["close"] < last_sl and prev["close"] >= last_sl and bear_sweep:
            bear_mss = True

    # FVG - كشف الفجوات
    bull_fvg_top = None
    bull_fvg_bot = None
    bear_fvg_top = None
    bear_fvg_bot = None
    if len(df_recent) >= 3:
        if last["low"] > df_recent["high"].iloc[-3]:
            bull_fvg_top = last["low"]
            bull_fvg_bot = df_recent["high"].iloc[-3]
        if last["high"] < df_recent["low"].iloc[-3]:
            bear_fvg_top = df_recent["low"].iloc[-3]
            bear_fvg_bot = last["high"]

    # Order Block - آخر شمعة عكسية قبل شمعة قوية
    bull_ob_high, bull_ob_low = None, None
    bear_ob_high, bear_ob_low = None, None
    if len(df_recent) >= 2:
        prev = df_recent.iloc[-2]
        if last["close"] > last["open"] and prev["close"] < prev["open"]:
            bull_ob_high = prev["high"]
            bull_ob_low = prev["low"]
        if last["close"] < last["open"] and prev["close"] > prev["open"]:
            bear_ob_high = prev["high"]
            bear_ob_low = prev["low"]

    # الجلسات النشطة
    sessions = get_active_sessions(current_time)
    if not sessions:
        return signals
    if in_blackout(current_time):
        return signals

    # فحص الحد اليومي وعدد الصفقات
    if state["trade_count_today"] >= MAX_TRADES_PER_DAY:
        return signals

    # فحص الكول داون
    if state["last_entry_time"]:
        last_entry_dt = datetime.fromisoformat(state["last_entry_time"])
        bars_since = int((current_time - last_entry_dt).total_seconds() / 300)
        cooldown = COOLDOWN_STRONG if (strong_bull or strong_bear) else COOLDOWN_NORMAL
        if bars_since < cooldown:
            return signals

    # ==================== شروط النماذج ====================
    # هنا نطبق نفس منطق Pine: نموذج الوقت + MSS + FVG/OB

    def try_signal(model_name, direction, entry, sl_level):
        sl_pts = abs(entry - sl_level) * MULT
        if sl_pts < MIN_SL_PTS or sl_pts > MAX_SL_PTS:
            return
        sl_dist = abs(entry - sl_level)
        if direction == "BUY":
            tp1 = entry + sl_dist * TP1_R
            tp2 = entry + sl_dist * TP2_R
            tp3 = entry + sl_dist * TP3_R
        else:
            tp1 = entry - sl_dist * TP1_R
            tp2 = entry - sl_dist * TP2_R
            tp3 = entry - sl_dist * TP3_R
        signals.append({
            "model": model_name,
            "direction": direction,
            "entry": round(entry, 2),
            "sl": round(sl_level, 2),
            "tp1": round(tp1, 2),
            "tp2": round(tp2, 2),
            "tp3": round(tp3, 2)
        })

    for sess in sessions:
        if sess in state["models_done_today"]:
            continue

        # Buy setups
        if trend_up and bull_mss:
            # أولوية: OB -> FVG -> CE
            if bull_ob_high is not None and last["low"] <= (bull_ob_high + bull_ob_low) / 2:
                entry = (bull_ob_high + bull_ob_low) / 2
                sl_level = bull_ob_low - atr * 0.3
                try_signal(sess, "BUY", entry, sl_level)
            elif bull_fvg_top is not None and last["low"] <= (bull_fvg_top + bull_fvg_bot) / 2:
                entry = (bull_fvg_top + bull_fvg_bot) / 2
                sl_level = bull_fvg_bot - atr * 0.3
                try_signal(sess, "BUY", entry, sl_level)

        # Sell setups
        if trend_down and bear_mss:
            if bear_ob_high is not None and last["high"] >= (bear_ob_high + bear_ob_low) / 2:
                entry = (bear_ob_high + bear_ob_low) / 2
                sl_level = bear_ob_high + atr * 0.3
                try_signal(sess, "SELL", entry, sl_level)
            elif bear_fvg_top is not None and last["high"] >= (bear_fvg_top + bear_fvg_bot) / 2:
                entry = (bear_fvg_top + bear_fvg_bot) / 2
                sl_level = bear_fvg_top + atr * 0.3
                try_signal(sess, "SELL", entry, sl_level)

    return signals


# ==================== الدالة الرئيسية ====================
def main():
    print("🤖 بدء التشغيل...")

    state = load_state()
    now_utc = datetime.now(ZoneInfo("UTC"))
    now_ny = now_utc.astimezone(NY_TZ)

    # إعادة تعيين العدادات عند بداية يوم جديد
    today = now_ny.date().isoformat()
    if state["last_day"] != today:
        state["trade_count_today"] = 0
        state["models_done_today"] = []
        state["last_day"] = today

    # جلب البيانات
    df5 = fetch_ohlc("5min", 500)
    df1h = fetch_ohlc("1h", 500)
    if df5 is None or df1h is None:
        send_telegram("❌ فشل جلب البيانات من Twelve Data")
        save_state(state)
        return

    current_price = float(df5.iloc[-1]["close"])
    print(f"السعر الحالي: {current_price} | الوقت NY: {now_ny.strftime('%H:%M')}")

    # 1. إذا فيه صفقة نشطة، نفحصها
    if state["active_trade"] is not None:
        check_active_trade(state, current_price, now_ny)
        save_state(state)
        return

    # 2. نفحص إشارات جديدة
    signals = detect_signals(df5, df1h, state, now_ny)
    if not signals:
        print("لا توجد إشارات حالياً.")
        save_state(state)
        return

    # 3. نأخذ أول إشارة فقط (كما في Pine: Max/Day)
    sig = signals[0]
    state["active_trade"] = {
        "model": sig["model"],
        "direction": sig["direction"],
        "entry": sig["entry"],
        "sl": sig["sl"],
        "tp1": sig["tp1"],
        "tp2": sig["tp2"],
        "tp3": sig["tp3"],
        "tp1_hit": False,
        "tp2_hit": False,
        "tp3_hit": False,
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
        f"الوقت: {now_ny.strftime('%H:%M')} NY"
    )

    save_state(state)
    print("✅ تم إرسال الإشارة وحفظ الحالة")


if __name__ == "__main__":
    main()