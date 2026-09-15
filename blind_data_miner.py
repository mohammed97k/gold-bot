import yfinance as yf
import pandas as pd
import numpy as np

print("=================================================================")
print("  المستكشف الكمي المستقل: التنقيب عن أنماط رياضية نقية للذهب    ")
print("=================================================================")

# 1. سحب بيانات 5 دقائق
print("[1/4] جاري تحميل مصفوفة الأسعار اللحظية...")
df = yf.download("GC=F", period="1mo", interval="5m", progress=False)
if df.empty:
    df = yf.download("XAUUSD=X", period="1mo", interval="5m", progress=False)

if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)
df = df.dropna()

if df.index.tz is None:
    df.index = df.index.tz_localize("UTC").tz_convert("Asia/Baghdad")
else:
    df.index = df.index.tz_convert("Asia/Baghdad")

# 2. تفكيك الشموع إلى متجهات رياضية بحتة
print("[2/4] تحويل الشموع إلى مصفوفات هندسية...")
c_range = df['High'] - df['Low']
c_range = np.where(c_range == 0, 0.01, c_range)

upper_wick = df['High'] - df[['Open', 'Close']].max(axis=1)
lower_wick = df[['Open', 'Close']].min(axis=1) - df['Low']

df['upper_ratio'] = upper_wick / c_range
df['lower_ratio'] = lower_wick / c_range
df['vol_expansion'] = c_range / pd.Series(c_range).rolling(12).mean()
df['hour'] = df.index.hour

# 3. محرك التنقيب الآلي
print("[3/4] تشغيل خوارزمية فحص الاحتمالات عبر آلاف التركيبات...")
best_setups = []

wick_thresholds = [0.40, 0.50, 0.60]
vol_thresholds = [1.0, 1.3, 1.6]
hour_windows = [(10, 14), (14, 18), (18, 22)]
target_rrs = [1.5, 2.0, 2.5]

for h_start, h_end in hour_windows:
    for w_thresh in wick_thresholds:
        for v_thresh in vol_thresholds:
            for rr in target_rrs:
                # نمط الشراء الرياضي
                cond_long = (df['hour'] >= h_start) & (df['hour'] <= h_end) & \
                            (df['lower_ratio'] >= w_thresh) & \
                            (df['vol_expansion'] >= v_thresh)
                
                outcomes = []
                for idx in np.where(cond_long)[0]:
                    if idx >= len(df) - 35:
                        continue
                    entry = df['Close'].iloc[idx]
                    sl = df['Low'].iloc[idx] - 0.5
                    risk = entry - sl
                    if risk < 1.0 or risk > 6.0:
                        continue
                    tp = entry + (risk * rr)
                    sub = df.iloc[idx+1:idx+36]
                    hit_tp = (sub['High'] >= tp).any()
                    hit_sl = (sub['Low'] <= sl).any()
                    if hit_tp and not hit_sl:
                        outcomes.append(1)
                    elif hit_sl and not hit_tp:
                        outcomes.append(0)
                    elif hit_tp and hit_sl:
                        outcomes.append(1 if (sub['High'] >= tp).idxmax() < (sub['Low'] <= sl).idxmax() else 0)

                if len(outcomes) >= 15:
                    winrate = (sum(outcomes) / len(outcomes)) * 100
                    net_r = (sum(outcomes) * rr) - (len(outcomes) - sum(outcomes))
                    best_setups.append({
                        'type': 'BUY',
                        'hours': f"{h_start}:00 - {h_end}:00",
                        'wick_thresh': w_thresh,
                        'vol_thresh': v_thresh,
                        'rr': rr,
                        'trades': len(outcomes),
                        'winrate': winrate,
                        'net_r': net_r
                    })

                # نمط البيع الرياضي
                cond_short = (df['hour'] >= h_start) & (df['hour'] <= h_end) & \
                             (df['upper_ratio'] >= w_thresh) & \
                             (df['vol_expansion'] >= v_thresh)
                
                outcomes_s = []
                for idx in np.where(cond_short)[0]:
                    if idx >= len(df) - 35:
                        continue
                    entry = df['Close'].iloc[idx]
                    sl = df['High'].iloc[idx] + 0.5
                    risk = sl - entry
                    if risk < 1.0 or risk > 6.0:
                        continue
                    tp = entry - (risk * rr)
                    sub = df.iloc[idx+1:idx+36]
                    hit_tp = (sub['Low'] <= tp).any()
                    hit_sl = (sub['High'] >= sl).any()
                    if hit_tp and not hit_sl:
                        outcomes_s.append(1)
                    elif hit_sl and not hit_tp:
                        outcomes_s.append(0)
                    elif hit_tp and hit_sl:
                        outcomes_s.append(1 if (sub['Low'] <= tp).idxmax() < (sub['High'] >= sl).idxmax() else 0)

                if len(outcomes_s) >= 15:
                    winrate_s = (sum(outcomes_s) / len(outcomes_s)) * 100
                    net_r_s = (sum(outcomes_s) * rr) - (len(outcomes_s) - sum(outcomes_s))
                    best_setups.append({
                        'type': 'SELL',
                        'hours': f"{h_start}:00 - {h_end}:00",
                        'wick_thresh': w_thresh,
                        'vol_thresh': v_thresh,
                        'rr': rr,
                        'trades': len(outcomes_s),
                        'winrate': winrate_s,
                        'net_r': net_r_s
                    })

# 4. فرز الأنماط الخمسة الأقوى
print("[4/4] استخراج أفضل 5 معادلات غير تقليدية تم اكتشافها:")
res_df = pd.DataFrame(best_setups)
if not res_df.empty:
    res_df = res_df.sort_values(by='net_r', ascending=False).head(5)
    print("-----------------------------------------------------------------")
    for i, r in res_df.reset_index(drop=True).iterrows():
        print(f"النمط #{i+1}: اتجاه [{r['type']}]")
        print(f"  • نافذة التوقيت: بتوقيت بغداد ({r['hours']})")
        print(f"  • شرط الذيل الرافض: نسبة الذيل >= {int(r['wick_thresh']*100)}% من كامل الشمعة")
        print(f"  • توسع الرينج (انفجار السيولة): ضعف الرينج المتوسط بمقدار >= {r['vol_thresh']}x")
        print(f"  • نسبة الهدف للمخاطرة (RR): 1:{r['rr']}")
        print(f"  • عدد الصفقات: {r['trades']} صفقة | نسبة الفوز: {r['winrate']:.1f}% | العائد الصافي: +{r['net_r']:.1f}R")
        print("-----------------------------------------------------------------")
