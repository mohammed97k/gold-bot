import yfinance as yf
import pandas as pd
import numpy as np

print("جاري تشريح وتصفية Mohamed Gemini v2...")

df = yf.download("GC=F", period="1mo", interval="5m")
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# توقيت بغداد (UTC+3)
df.index = df.index.tz_convert("Asia/Baghdad")

# حساب المدى والمتوسطات
df['range'] = df['High'] - df['Low']
df['body'] = abs(df['Close'] - df['Open'])
df['upper_wick'] = df['High'] - df[['Open', 'Close']].max(axis=1)
df['lower_wick'] = df[['Open', 'Close']].min(axis=1) - df['Low']

# مؤشر ATR
high_low = df['High'] - df['Low']
high_cp = (df['High'] - df['Close'].shift()).abs()
low_cp = (df['Low'] - df['Close'].shift()).abs()
df['tr'] = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
df['atr'] = df['tr'].rolling(14).mean()

df['ema50'] = df['Close'].ewm(span=50, adjust=False).mean()
df['ema200'] = df['Close'].ewm(span=200, adjust=False).mean()

# 1. فلتر الجلسات: من 9 صباحاً إلى 7 مساءً بتوقيت بغداد
session_filter = (df.index.hour >= 9) & (df.index.hour <= 19)

# 2. فلتر شمعة السيولة: ذيل يمثل 55% فأكثر وحجم الشمعة محترم مقارنة بالـ ATR
liq_bull = (df['lower_wick'] / df['range'] >= 0.55) & (df['range'] >= df['atr'] * 0.8)
liq_bear = (df['upper_wick'] / df['range'] >= 0.55) & (df['range'] >= df['atr'] * 0.8)

# 3. الاتجاه العام القوي
trend_bull = (df['Close'] > df['ema50']) & (df['ema50'] > df['ema200'])
trend_bear = (df['Close'] < df['ema50']) & (df['ema50'] < df['ema200'])

long_cond = session_filter & trend_bull & liq_bull & (df['Close'] > df['Open'])
short_cond = session_filter & trend_bear & liq_bear & (df['Close'] < df['Open'])

trades = []
rr = 2.0

for i in range(len(df) - 50):
    if long_cond.iloc[i]:
        entry = df['Close'].iloc[i]
        sl = df['Low'].iloc[i] - 0.5
        risk = entry - sl
        if 1.5 <= risk <= 6.0:
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
        sl = df['High'].iloc[i] + 0.5
        risk = sl - entry
        if 1.5 <= risk <= 6.0:
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
    daily_trades = total / 22
    net_r = (wins * rr) - (total - wins)
    print("\n===============================")
    print(f"إجمالي الصفقات المصفاة: {total}")
    print(f"معدل الصفقات اليومي: {daily_trades:.1f} صفقة/يوم")
    print(f"الصفقات الرابحة: {wins} | الصفقات الخاسرة: {total - wins}")
    print(f"نسبة الفوز (Win Rate): {winrate:.1f}%")
    print(f"صافي العائد: +{net_r:.1f}R")
    print("===============================")
