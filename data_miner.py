import yfinance as yf
import pandas as pd
import numpy as np

print("جاري تشريح MSNR المؤسسي (الاتجاه 4H + مناطق 1H + تأكيد 30M)...")

# سحب بيانات الفريمات الثلاثة
df_4h = yf.download("GC=F", period="2mo", interval="1h")  # سنبني منها الـ 4 ساعات لضمان الدقة
df_1h = yf.download("GC=F", period="1mo", interval="1h")
df_30m = yf.download("GC=F", period="1mo", interval="30m")

if df_1h.empty or df_30m.empty:
    df_4h = yf.download("XAUUSD=X", period="2mo", interval="1h")
    df_1h = yf.download("XAUUSD=X", period="1mo", interval="1h")
    df_30m = yf.download("XAUUSD=X", period="1mo", interval="30m")

for d in [df_4h, df_1h, df_30m]:
    if isinstance(d.columns, pd.MultiIndex):
        d.columns = d.columns.get_level_values(0)
    if d.index.tz is None:
        d.index = d.index.tz_localize("UTC").tz_convert("Asia/Baghdad")
    else:
        d.index = d.index.tz_convert("Asia/Baghdad")

# 1. بناء اتجاه فريم الـ 4 ساعات (4H Trend)
df_4h_res = df_4h.resample('4h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'}).dropna()
df_4h_res['ema50_4h'] = df_4h_res['Close'].ewm(span=50, adjust=False).mean()
df_4h_res['trend_4h'] = np.where(df_4h_res['Close'] > df_4h_res['ema50_4h'], 1, -1)

# 2. تحديد قمم وقيعان الساعة (1H Support & Resistance)
lookback_1h = 24
df_1h['h1_high'] = df_1h['High'].rolling(lookback_1h).max().shift(1)
df_1h['h1_low'] = df_1h['Low'].rolling(lookback_1h).min().shift(1)

# دمج اتجاه 4H ومستويات 1H مع فريم 30M
df = pd.merge_asof(df_30m.sort_index(), df_1h[['h1_high', 'h1_low']].sort_index(), left_index=True, right_index=True)
df = pd.merge_asof(df.sort_index(), df_4h_res[['trend_4h']].sort_index(), left_index=True, right_index=True)

df['range'] = df['High'] - df['Low']
df['upper_wick'] = df['High'] - df[['Open', 'Close']].max(axis=1)
df['lower_wick'] = df[['Open', 'Close']].min(axis=1) - df['Low']

# ساعات العمل (لندن ونيويورك: 10 ص إلى 8 م بتوقيت بغداد)
session = (df.index.hour >= 10) & (df.index.hour <= 20)

# شروط الدخول المتوافقة مع اتجاه الـ 4 ساعات:
# شراء: اتجاه 4H صاعد + كسر قاع الساعة بذيل ارتدادي وإغلاق أخضر
long_cond = session & (df['trend_4h'] == 1) & (df['Low'] < df['h1_low']) & (df['Close'] > df['h1_low']) & (df['lower_wick'] / df['range'] >= 0.38) & (df['Close'] > df['Open'])

# بيع: اتجاه 4H هابط + كسر قمة الساعة بذيل ارتدادي وإغلاق أحمر
short_cond = session & (df['trend_4h'] == -1) & (df['High'] > df['h1_high']) & (df['Close'] < df['h1_high']) & (df['upper_wick'] / df['range'] >= 0.38) & (df['Close'] < df['Open'])

trades = []
rr = 2.0

for i in range(len(df) - 40):
    if long_cond.iloc[i]:
        entry = df['Close'].iloc[i]
        sl = df['Low'].iloc[i] - 1.0
        risk = entry - sl
        if 5.0 <= risk <= 13.0:  # نطاق الستوب 50 إلى 130 نقطة
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
        if 5.0 <= risk <= 13.0:
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
    print(f"إجمالي صفقات MSNR المؤسسية: {total}")
    print(f"معدل الصفقات اليومي: {daily_trades:.2f} صفقة/يوم")
    print(f"الصفقات الرابحة: {wins} | الصفقات الخاسرة: {total - wins}")
    print(f"نسبة الفوز (Win Rate): {winrate:.1f}%")
    print(f"صافي العائد: +{net_r:.1f}R")
    print("===============================")
else:
    print("لم تتطابق أي فرصة مع اتجاه 4H الصارم ومستويات 1H في هذه الفترة.")
