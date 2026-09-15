import yfinance as yf
import pandas as pd
import numpy as np

print("جاري سحب بيانات الذهب التاريخية...")

# سحب بيانات الذهب (GC=F هو عقد الذهب الآجل في ياهو فاينانس)
gold_5m = yf.download("GC=F", period="1mo", interval="5m")
gold_1h = yf.download("GC=F", period="6mo", interval="1h")

if gold_5m.empty or gold_1h.empty:
    print("فشل جلب البيانات، يرجى التأكد من الاتصال.")
    exit()

print(f"تم سحب {len(gold_5m)} شمعة 5 دقائق، و {len(gold_1h)} شمعة ساعة.")

# تسطيح الأعمدة إذا كانت MultiIndex
if isinstance(gold_5m.columns, pd.MultiIndex):
    gold_5m.columns = gold_5m.columns.get_level_values(0)
if isinstance(gold_1h.columns, pd.MultiIndex):
    gold_1h.columns = gold_1h.columns.get_level_values(0)

# حساب متوسط حجم الذيول مقارنة بجسم الشمعة
gold_5m['body'] = abs(gold_5m['Close'] - gold_5m['Open'])
gold_5m['upper_wick'] = gold_5m['High'] - gold_5m[['Open', 'Close']].max(axis=1)
gold_5m['lower_wick'] = gold_5m[['Open', 'Close']].min(axis=1) - gold_5m['Low']
gold_5m['candle_range'] = gold_5m['High'] - gold_5m['Low']

print("\n--- نتائج تشريح الشموع ---")
print(f"متوسط مدى شمعة 5 دقائق: {gold_5m['candle_range'].mean():.2f} دولار")
print(f"متوسط حجم الجسم: {gold_5m['body'].mean():.2f} دولار")
print(f"متوسط الذيل العلوي: {gold_5m['upper_wick'].mean():.2f} دولار")
print(f"متوسط الذيل السفلي: {gold_5m['lower_wick'].mean():.2f} دولار")

# فحص نموذج الشمعة الارتدادية: ذيل يمثل أكثر من 60% من المدى
pinbar_bull = (gold_5m['lower_wick'] / gold_5m['candle_range'] > 0.6) & (gold_5m['Close'] > gold_5m['Open'])
pinbar_bear = (gold_5m['upper_wick'] / gold_5m['candle_range'] > 0.6) & (gold_5m['Close'] < gold_5m['Open'])

print(f"\nتكرار شمعة الرفض الصاعدة (Hammer/Pinbar): {pinbar_bull.sum()} مرة بالشهر")
print(f"تكرار شمعة الرفض الهابطة (Shooting Star): {pinbar_bear.sum()} مرة بالشهر")

daily_setups = (pinbar_bull.sum() + pinbar_bear.sum()) / 22
print(f"معدل تشكل هذه الشموع يومياً: {daily_setups:.1f} فرصة/يوم")
