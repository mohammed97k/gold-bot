import yfinance as yf
import pandas as pd
import numpy as np

print("جاري تشريح استراتيجية MSNR المتقدمة على الذهب...")

# سحب 5000+ شمعة على فريم 5 دقائق
df = yf.download("GC=F", period="1mo", interval="5m")
if df.empty:
    df = yf.download("XAUUSD=X", period="1mo", interval="5m")

if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

# توحيد التوقيت لبغداد
if df.index.tz is None:
    df.index = df.index.tz_localize("UTC").tz_convert("Asia/Baghdad")
else:
    df.index = df.index.tz_convert("Asia/Baghdad")

# ساعات السيولة العالية (لندن ونيويورك: 10:00 صباحاً إلى 08:00 مساءً)
session = (df.index.hour >= 10) & (df.index.hour <= 20)

# استخراج القمم والقيعان البنيوية (Swing High / Swing Low) لنطاق 15 شمعة
lookback = 15
df['swing_high'] = df['High'].rolling(lookback).max().shift(1)
df['swing_low'] = df['Low'].rolling(lookback).min().shift(1)

# شروط MSNR:
# 1. كسر سائل للقاع ثم إغلاق أعلاه (MSNR Bullish Sweep)
bull_sweep = (df['Low'] < df['swing_low']) & (df['Close'] > df['swing_low']) & (df['Close'] > df['Open'])
# 2. كسر سائل للقمة ثم إغلاق أدناها (MSNR Bearish Sweep)
bear_sweep = (df['High'] > df['swing_high']) & (df['Close'] < df['swing_high']) & (df['Close'] < df['Open'])

long_cond = session & bull_sweep
short_cond = session & bear_sweep

trades = []
rr = 2.0

for i in range(len(df) - 40):
    if long_cond.iloc[i]:
        entry = df['Close'].iloc[i]
        sl = df['Low'].iloc[i] - 0.5
        risk = entry - sl
        # فلتر المخاطرة المعقولة (بين 2.0$ و 8.0$ على فريم 5 دقائق)
        if 2.0 <= risk <= 8.0:
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
        if 2.0 <= risk <= 8.0:
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
    print(f"إجمالي صفقات MSNR: {total}")
    print(f"معدل الصفقات اليومي: {daily_trades:.2f} صفقة/يوم")
    print(f"الصفقات الرابحة: {wins} | الصفقات الخاسرة: {total - wins}")
    print(f"نسبة الفوز (Win Rate): {winrate:.1f}%")
    print(f"صافي العائد: +{net_r:.1f}R")
    print("===============================")
else:
    print("لم يتم العثور على صفقات تطابق الشروط.")
