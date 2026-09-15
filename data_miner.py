import yfinance as yf
import pandas as pd
import numpy as np

print("جاري فحص استراتيجية Mohamed Gemini المؤسسية (15M + 1H)...")

# سحب بيانات 15 دقيقة وبيانات الساعة
df_15m = yf.download("GC=F", period="2mo", interval="15m")
df_1h = yf.download("GC=F", period="2mo", interval="1h")

if isinstance(df_15m.columns, pd.MultiIndex):
    df_15m.columns = df_15m.columns.get_level_values(0)
if isinstance(df_1h.columns, pd.MultiIndex):
    df_1h.columns = df_1h.columns.get_level_values(0)

df_15m.index = df_15m.index.tz_convert("Asia/Baghdad")
df_1h.index = df_1h.index.tz_convert("Asia/Baghdad")

# استخراج قمة وقاع شمعة الساعة السابقة
df_1h['prev_1h_high'] = df_1h['High'].shift(1)
df_1h['prev_1h_low'] = df_1h['Low'].shift(1)

# دمج مستويات الساعة مع فريم 15 دقيقة
df = pd.merge_asof(df_15m.sort_index(), df_1h[['prev_1h_high', 'prev_1h_low']].sort_index(), left_index=True, right_index=True)

df['range'] = df['High'] - df['Low']
df['upper_wick'] = df['High'] - df[['Open', 'Close']].max(axis=1)
df['lower_wick'] = df[['Open', 'Close']].min(axis=1) - df['Low']
df['ema50'] = df['Close'].ewm(span=50, adjust=False).mean()

# توقيت العمل: جلسة لندن ونيويورك فقط (10:00 إلى 20:00 بتوقيت بغداد)
session = (df.index.hour >= 10) & (df.index.hour <= 20)

# كسر سيولة الساعة والارتداد بشمعة ذات ذيل
long_cond = session & (df['Low'] < df['prev_1h_low']) & (df['Close'] > df['prev_1h_low']) & (df['lower_wick'] / df['range'] >= 0.45) & (df['Close'] > df['Open'])
short_cond = session & (df['High'] > df['prev_1h_high']) & (df['Close'] < df['prev_1h_high']) & (df['upper_wick'] / df['range'] >= 0.45) & (df['Close'] < df['Open'])

trades = []
rr = 2.0

for i in range(len(df) - 40):
    if long_cond.iloc[i]:
        entry = df['Close'].iloc[i]
        sl = df['Low'].iloc[i] - 1.0
        risk = entry - sl
        # تصفية الستوب ليكون بين 6.0$ و 13.0$ (60 إلى 130 نقطة)
        if 6.0 <= risk <= 13.0:
            tp = entry + (risk * rr)
            future = df.iloc[i+1:i+40]
            hit_tp = (future['High'] >= tp).any()
            hit_sl = (future['Low'] <= sl).any()
            if hit_tp and not hit_sl:
                trades.append(1)
            elif hit_sl and not hit_tp:
                trades.append(0)
            elif hit_tp and hit_sl:
                trades.append(1 if (future['High'] >= tp).idxmax() < (future['Low'] <= sl).idxmax() else 0)

    elif short_cond.iloc[i]:
        entry = df['Close'].iloc[i]
        sl = df['High'].iloc[i] + 1.0
        risk = sl - entry
        if 6.0 <= risk <= 13.0:
            tp = entry - (risk * rr)
            future = df.iloc[i+1:i+40]
            hit_tp = (future['Low'] <= tp).any()
            hit_sl = (future['High'] >= sl).any()
            if hit_tp and not hit_sl:
                trades.append(1)
            elif hit_sl and not hit_tp:
                trades.append(0)
            elif hit_tp and hit_sl:
                trades.append(1 if (future['Low'] <= tp).idxmax() < (future['High'] >= sl).idxmax() else 0)

if trades:
    wins = sum(trades)
    total = len(trades)
    winrate = (wins / total) * 100
    daily_trades = total / 44
    net_r = (wins * rr) - (total - wins)
    print("\n===============================")
    print(f"إجمالي الصفقات (خلال شهرين): {total}")
    print(f"معدل الصفقات اليومي: {daily_trades:.2f} صفقة/يوم")
    print(f"الصفقات الرابحة: {wins} | الصفقات الخاسرة: {total - wins}")
    print(f"نسبة الفوز (Win Rate): {winrate:.1f}%")
    print(f"صافي العائد: +{net_r:.1f}R")
    print("===============================")
