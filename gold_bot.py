import os
import json
import requests
import numpy as np
import pandas as pd
import yfinance as yf

# ────────────────────────────────────
# Settings & Parameters
# ────────────────────────────────────
SYMBOL = "GC=F"  # رمز عقود الذهب الآجلة من Yahoo Finance (مطابق لتحركات XAUUSD)
PIVOT_LEN = 5
MAX_LEVELS = 80
SL_BUFFER_PTS = 10.0
POINT_SIZE = 0.01
ACTIVE_LOOKBACK = 120
BREAKOUT_LOOKBACK = 80
REJECTION_WINDOW = 3
USE_LIQUIDITY = False
USE_DAILY_FILTER = True
STATE_FILE = "bot_state.json"

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_alert(msg: str):
    if not TELEGRAM_TOKEN or not CHAT_ID:
        print("[!] خطأ: بيانات التيليجرام غير محددة في Secrets.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": msg,
        "parse_mode": "Markdown"
    }
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("[+] تم إرسال الإشارة بنجاح إلى التلغرام.")
        else:
            print(f"[!] فشل إرسال الإشعار: {res.text}")
    except Exception as e:
        print(f"[!] استثناء أثناء الإرسال: {e}")

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"last_alert_time": "", "pending": None}

def save_state(state):
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f)
    except Exception as e:
        print(f"[!] تعذر حفظ الحالة: {e}")

# ────────────────────────────────────
# Fetch Market Data
# ────────────────────────────────────
print("[*] جاري تحميل بيانات الذهب...")
m30_df = yf.download(SYMBOL, interval="30m", period="1mo", progress=False)
h4_df = yf.download(SYMBOL, interval="1h", period="3mo", progress=False) # تجميع H4
daily_df = yf.download(SYMBOL, interval="1d", period="6mo", progress=False)

if m30_df.empty or len(m30_df) < 50:
    print("[!] تعذر جلب بيانات الشموع الكافية.")
    exit(0)

# تنظيف الأعمدة إذا كانت MultiIndex
if isinstance(m30_df.columns, pd.MultiIndex):
    m30_df.columns = m30_df.columns.get_level_values(0)
if isinstance(h4_df.columns, pd.MultiIndex):
    h4_df.columns = h4_df.columns.get_level_values(0)
if isinstance(daily_df.columns, pd.MultiIndex):
    daily_df.columns = daily_df.columns.get_level_values(0)

# إعادة تجميع H4 من شموع الساعة
h4_df = h4_df.resample('4h').agg({
    'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'
}).dropna()

# ────────────────────────────────────
# HTF Trend Evaluation
# ────────────────────────────────────
# اتجاه Daily
d_close1 = daily_df['Close'].iloc[-2]
d_close2 = daily_df['Close'].iloc[-3]
daily_bull = d_close1 > d_close2
daily_bear = d_close1 < d_close2

# اتجاه H4
h4_close1 = h4_df['Close'].iloc[-2]
h4_high2 = h4_df['High'].iloc[-3]
h4_low2 = h4_df['Low'].iloc[-3]

h4_direction = 0
if h4_close1 > h4_high2:
    h4_direction = 1
elif h4_close1 < h4_low2:
    h4_direction = -1

trend_bull = (h4_direction == 1) and (not USE_DAILY_FILTER or daily_bull)
trend_bear = (h4_direction == -1) and (not USE_DAILY_FILTER or daily_bear)

print(f"[*] Trend H4: {h4_direction} | Trend Daily Bull: {daily_bull} | Bear: {daily_bear}")

# ────────────────────────────────────
# Level Detection & Calculations
# ────────────────────────────────────
levels = []  # قائمة المستويات: dict(top, bot, dir, born, fresh, active, breakout, strong)

opens = m30_df['Open'].values
highs = m30_df['High'].values
lows = m30_df['Low'].values
closes = m30_df['Close'].values
n_bars = len(m30_df)

def add_level(top, bot, dir_val, bar_idx):
    t = max(top, bot)
    b = min(top, bot)
    for lvl in levels:
        if lvl['dir'] == dir_val and abs(lvl['top'] - t) <= POINT_SIZE and abs(lvl['bot'] - b) <= POINT_SIZE:
            return
    if t > b:
        levels.append({
            'top': t, 'bot': b, 'dir': dir_val,
            'born': bar_idx, 'fresh': True,
            'active': False, 'breakout': False, 'strong': False
        })
        if len(levels) > MAX_LEVELS:
            levels.pop(0)

# حساب الـ Pivots
pivot_highs = [None] * n_bars
pivot_lows = [None] * n_bars
for i in range(PIVOT_LEN, n_bars - PIVOT_LEN):
    if all(highs[i] > highs[i - k] for k in range(1, PIVOT_LEN + 1)) and \
       all(highs[i] >= highs[i + k] for k in range(1, PIVOT_LEN + 1)):
        pivot_highs[i] = highs[i]
    if all(lows[i] < lows[i - k] for k in range(1, PIVOT_LEN + 1)) and \
       all(lows[i] <= lows[i + k] for k in range(1, PIVOT_LEN + 1)):
        pivot_lows[i] = lows[i]

# استخراج المستويات من حركة السعر
for i in range(10, n_bars):
    bull1 = closes[i-1] > opens[i-1]
    bull2 = closes[i] > opens[i]
    bear1 = closes[i-1] < opens[i-1]
    bear2 = closes[i] < opens[i]

    # Classic
    if bull1 and bull2:
        add_level(max(opens[i-1], closes[i-1]), min(opens[i-1], closes[i-1]), 1, i)
    if bear1 and bear2:
        add_level(max(opens[i-1], closes[i-1]), min(opens[i-1], closes[i-1]), -1, i)

    # A/V
    if bear1 and bull2:
        add_level(max(opens[i-1], closes[i-1]), min(opens[i-1], closes[i-1]), 1, i)
    if bull1 and bear2:
        add_level(max(opens[i-1], closes[i-1]), min(opens[i-1], closes[i-1]), -1, i)

    # Gap
    if bull1 and bull2 and lows[i] > highs[i-1]:
        add_level(lows[i], highs[i-1], 1, i)
    if bear1 and bear2 and highs[i] < lows[i-1]:
        add_level(lows[i-1], highs[i], -1, i)

# فحص كفاءة المستويات (Level Qualification)
curr_bar = n_bars - 1
for lvl in levels:
    # Fresh check
    for b in range(lvl['born'] + 1, n_bars):
        if highs[b] >= lvl['bot'] and lows[b] <= lvl['top']:
            lvl['fresh'] = False
            break

    # Active check
    if not lvl['active'] and (curr_bar - lvl['born'] <= ACTIVE_LOOKBACK):
        for older in levels:
            if older['born'] < lvl['born'] and older['dir'] != lvl['dir']:
                if max(lvl['bot'], older['bot']) <= min(lvl['top'], older['top']):
                    lvl['active'] = True
                    break

    # Breakout check
    if not lvl['breakout'] and (curr_bar - lvl['born'] <= BREAKOUT_LOOKBACK):
        look_start = max(0, curr_bar - (PIVOT_LEN * 2))
        if lvl['dir'] == 1:
            lvl['breakout'] = closes[curr_bar] > np.max(highs[look_start:curr_bar])
        else:
            lvl['breakout'] = closes[curr_bar] < np.min(lows[look_start:curr_bar])

    lvl['strong'] = lvl['fresh'] and lvl['active'] and lvl['breakout']

# ────────────────────────────────────
# Rejection & Retest Execution Engine
# ────────────────────────────────────
state = load_state()
pending = state.get("pending")
last_bar_time = str(m30_df.index[-1])

# شروط الـ Rejection
def bull_rejection(top, bot, h, l, o, c):
    return (h >= bot and l <= top) and (c > o) and (c >= bot) and (c > (h + l) / 2.0)

def bear_rejection(top, bot, h, l, o, c):
    return (h >= bot and l <= top) and (c < o) and (c <= top) and (c < (h + l) / 2.0)

# فحص تشكل رفض جديد إذا لم يكن هناك Pending
if not pending:
    chosen_lvl = None
    best_dist = float('inf')

    for lvl in levels:
        if not lvl['strong']:
            continue
        v_dir = (lvl['dir'] == 1 and trend_bull) or (lvl['dir'] == -1 and trend_bear)
        if not v_dir:
            continue

        rej = False
        if lvl['dir'] == 1:
            rej = bull_rejection(lvl['top'], lvl['bot'], highs[-1], lows[-1], opens[-1], closes[-1])
        else:
            rej = bear_rejection(lvl['top'], lvl['bot'], highs[-1], lows[-1], opens[-1], closes[-1])

        if rej:
            d = abs(closes[-1] - (lvl['top'] + lvl['bot']) / 2.0)
            if d < best_dist:
                best_dist = d
                chosen_lvl = lvl

    if chosen_lvl:
        dir_c = chosen_lvl['dir']
        recent_pl = [p for p in pivot_lows[-30:] if p is not None]
        recent_ph = [p for p in pivot_highs[-30:] if p is not None]
        last_swing = recent_pl[-1] if dir_c == 1 and recent_pl else (recent_ph[-1] if recent_ph else closes[-1])
        wave = abs(closes[-1] - last_swing)

        sl = (lows[-1] - SL_BUFFER_PTS * POINT_SIZE) if dir_c == 1 else (highs[-1] + SL_BUFFER_PTS * POINT_SIZE)
        tp1 = (closes[-1] + wave * 0.50) if dir_c == 1 else (closes[-1] - wave * 0.50)
        tp2 = (closes[-1] + wave * 1.00) if dir_c == 1 else (closes[-1] - wave * 1.00)

        pending = {
            "dir": dir_c,
            "bar_idx": curr_bar,
            "top": chosen_lvl['top'],
            "bot": chosen_lvl['bot'],
            "entry_ref": float(closes[-1]),
            "sl": round(float(sl), 2),
            "tp1": round(float(tp1), 2),
            "tp2": round(float(tp2), 2)
        }
        state["pending"] = pending
        print(f"[*] تم رصد Rejection مناسب عند مستوى: {chosen_lvl['top']} - {chosen_lvl['bot']}. في انتظار الـ Retest...")

# فحص تأكيد الـ Retest (خلال شمعتين أو 3 بعد الرفض)
elif pending:
    bars_after = curr_bar - pending["bar_idx"]
    zone_touched = highs[-1] >= pending["bot"] and lows[-1] <= pending["top"]
    confirm_buy = (pending["dir"] == 1 and zone_touched and closes[-1] > opens[-1] and closes[-1] > pending["entry_ref"])
    confirm_sell = (pending["dir"] == -1 and zone_touched and closes[-1] < opens[-1] and closes[-1] < pending["entry_ref"])

    if 1 <= bars_after <= REJECTION_WINDOW and (confirm_buy or confirm_sell):
        order_type = "🟢 شراء (BUY)" if pending["dir"] == 1 else "🔴 بيع (SELL)"
        entry_price = round(float(closes[-1]), 2)
        
        # منع تكرار الإشارة لنفس الشمعة
        if state.get("last_alert_time") != last_bar_time:
            msg = (
                f"🚨 *إشارة تداول جديدة - MSNR XAUUSD*\n\n"
                f"*النوع:* {order_type}\n"
                f"*سعر الدخول:* `{entry_price}`\n"
                f"*وقف الخسارة (SL):* `{pending['sl']}`\n"
                f"*الهدف الأول (TP1):* `{pending['tp1']}`\n"
                f"*الهدف الثاني (TP2):* `{pending['tp2']}`\n\n"
                f"⏱ *فريم:* M30\n"
                f"📅 *توقيت الإغلاق:* `{last_bar_time}`"
            )
            send_telegram_alert(msg)
            state["last_alert_time"] = last_bar_time

        state["pending"] = None  # إنهاء المعلق بعد الدخول

    elif bars_after > REJECTION_WINDOW:
        print("[*] انتهت نافذة الـ Retest دون تأكيد، تم إلغاء الإعداد المعلق.")
        state["pending"] = None

save_state(state)
print("[*] اكتمل الفحص بنجاح.")
