import yfinance as yf
import pandas as pd
import numpy as np

print("جاري تشريح استراتيجية Mohamed Gemini المؤسسية (1H FVG/OB + 15M Rejection)...")

# سحب البيانات لفريم الساعة والـ 15 دقيقة
df_1h = yf.download("GC=F", period="1mo", interval="1h")
df_15m = yf.download("GC=F", period="1mo", interval="15m")

if df_1h.empty or df_15m.empty:
    df_1h = yf.download("XAUUSD=X", period="1mo", interval="1h")
    df_15m = yf.download("XAUUSD=X", period="1mo", interval="15m")

if isinstance(df_1h.columns, pd.MultiIndex):
    df_1h.columns = df_1h.columns.get_level_values(0)
if isinstance(df_15m.columns, pd.MultiIndex):
    df_15m.columns = df_15m.columns.get_level_values(0)

# توحيد التوقيت لبغداد
for d in [df_1h, df_15m]:
    if d.index.tz is None:
        d.index = d.index.tz_localize("UTC").tz_convert("Asia/Baghdad")
    else:
        d.index = d.index.tz_convert("Asia/Baghdad")

# 1. استخراج مناطق FVG على فريم الساعة
# FVG شرائية: قاع الشمعة الحالية أعلى من قمة الشمعة قبل السابقة
bull_fvg_top = df_1h['Low']
bull_fvg_bottom = df_1h['High'].shift(2)
is_bull_fvg = bull_fvg_top > bull_fvg_bottom

# FVG بيعية: قمة الشمعة الحالية أدنى من قاع الشمعة قبل السابقة
bear_fvg_top = df_1h['Low'].shift(2)
bear_fvg_bottom = df_1h['High']
is_bear_fvg = bear_fvg_top > bear_fvg_bottom

df_1h['fvg_bull_top'] = np.where(is_bull_fvg, bull_fvg_top, np.nan)
df_1h['fvg_bull_bottom'] = np.where(is_bull_fvg, bull_fvg_bottom, np.nan)
df_1h['fvg_bear_top'] = np.where(is_bear_fvg, bear_fvg_top, np.nan)
df_1h['fvg_bear_bottom'] = np.where(is_bear_fvg, bear_fvg_bottom, np.nan)

# تمرير أحدث منطقة نشطة للأمام
fvg_levels = df_1h[['fvg_bull_top', 'fvg_bull_bottom', 'fvg_bear_top', 'fvg_bear_bottom']].ffill()

# دمج مناطق الساعة مع فريم 15 دقيقة
df = pd.merge_asof(df_15m.sort_index(), fvg_levels.sort_index(), left_index=True, right_index=True)

df['range'] = df['High'] - df['Low']
df['upper_wick'] = df['High'] - df[['Open', 'Close']].max(axis=1)
df['lower_wick'] = df[['Open', 'Close']].min(axis=1) - df['Low']

# ساعات العمل (لندن ونيويورك)
session = (df.index.hour >= 9) & (df.index.hour <= 20)

# شروط الدخول:
# شراء: السعر يختبر FVG صاعدة للساعة + يرتد بذيل سفلي واضح على فريم 15M
test_bull_fvg = (df['Low'] <= df['fvg_bull_top']) & (df['Close'] >= df['fvg_bull_bottom'])
rej_bull = (df['lower_wick'] / df['range'] >= 0.40) & (df['Close'] > df['Open'])
long_cond = session & test_bull_fvg & rej_bull

# بيع: السعر يختبر FVG هابطة للساعة + يرتد بذيل علوي واضح على فريم 15M
test_bear_fvg = (df['High'] >= df['fvg_bear_bottom']) & (df['Close'] <= df['fvg_bear_top'])
rej_bear = (df['upper_wick'] / df['range'] >= 0.40) & (df['Close'] < df['Open'])
short_cond = session & test_bear_fvg & rej_bear

trades = []
rr = 2.0

for i in range(len(df) - 40):
    if long_cond.iloc[i]:
        entry = df['Close'].iloc[i]
        sl = min(df['Low'].iloc[i], df['fvg_bull_bottom'].iloc[i]) - 1.0
        risk = entry - sl
        if 6.0 <= risk <= 13.0:  # نطاق الستوب المطلوب (60 إلى 130 نقطة)
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
        sl = max(df['High'].iloc[i], df['fvg_bear_top'].iloc[i]) + 1.0
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
    daily_trades = total / 22
    net_r = (wins * rr) - (total - wins)
    print("\n===============================")
    print(f"إجمالي الصفقات: {total}")
    print(f"معدل الصفقات اليومي: {daily_trades:.2f} صفقة/يوم")
    print(f"الصفقات الرابحة: {wins} | الصفقات الخاسرة: {total - wins}")
    print(f"نسبة الفوز (Win Rate): {winrate:.1f}%")
    print(f"صافي العائد: +{net_r:.1f}R")
    print("===============================")
else:
    print("لا توجد صفقات تطابق هذا النطاق من الستوب والشروط.")
