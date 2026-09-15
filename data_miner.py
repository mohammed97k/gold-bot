import yfinance as yf
import pandas as pd
import numpy as np

print("جاري تشريح استراتيجية Mohamed Gemini...")

df = yf.download("GC=F", period="1mo", interval="5m")
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# حساب المؤشرات
df['range'] = df['High'] - df['Low']
df['body'] = abs(df['Close'] - df['Open'])
df['upper_wick'] = df['High'] - df[['Open', 'Close']].max(axis=1)
df['lower_wick'] = df[['Open', 'Close']].min(axis=1) - df['Low']
df['ema50'] = df['Close'].ewm(span=50, adjust=False).mean()
df['ema200'] = df['Close'].ewm(span=200, adjust=False).mean()

# شروط الدخول لـ Mohamed Gemini:
# رفض سعري واضح (ذيل يمثل 50% فأكثر من الشمعة) مع اتجاه الـ EMA
long_cond = (df['lower_wick'] / df['range'] >= 0.50) & (df['Close'] > df['Open']) & (df['Close'] > df['ema50']) & (df['ema50'] > df['ema200'])
short_cond = (df['upper_wick'] / df['range'] >= 0.50) & (df['Close'] < df['Open']) & (df['Close'] < df['ema50']) & (df['ema50'] < df['ema200'])

trades = []
rr = 2.0

for i in range(len(df) - 50):
    if long_cond.iloc[i]:
        entry = df['Close'].iloc[i]
        sl = df['Low'].iloc[i] - 0.5
        risk = entry - sl
        if 1.5 <= risk <= 6.0:
            tp = entry + (risk * rr)
            # فحص النتيجة في الشموع التالية
            future = df.iloc[i+1:i+40]
            hit_tp = (future['High'] >= tp).any()
            hit_sl = (future['Low'] <= sl).any()
            if hit_tp and not hit_sl:
                trades.append(1)
            elif hit_sl and not hit_tp:
                trades.append(0)
            elif hit_tp and hit_sl:
                # من لمس أولاً
                tp_idx = (future['High'] >= tp).idxmax()
                sl_idx = (future['Low'] <= sl).idxmax()
                trades.append(1 if tp_idx < sl_idx else 0)

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
                tp_idx = (future['Low'] <= tp).idxmax()
                sl_idx = (future['High'] >= sl).idxmax()
                trades.append(1 if tp_idx < sl_idx else 0)

if trades:
    wins = sum(trades)
    total = len(trades)
    winrate = (wins / total) * 100
    daily_trades = total / 22
    net_r = (wins * rr) - (total - wins)
    print("\n===============================")
    print(f"إجمالي الصفقات خلال شهر: {total}")
    print(f"معدل الصفقات اليومي: {daily_trades:.1f} صفقة/يوم")
    print(f"الصفقات الرابحة: {wins} | الصفقات الخاسرة: {total - wins}")
    print(f"نسبة الفوز (Win Rate): {winrate:.1f}%")
    print(f"صافي العائد: +{net_r:.1f}R")
    print("===============================")
