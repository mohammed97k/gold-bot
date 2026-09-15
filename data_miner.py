import yfinance as yf
import pandas as pd
import numpy as np

print("جاري فحص Mohamed Gemini v3 (تأكيد الكسر + التأمين)...")

df = yf.download("GC=F", period="1mo", interval="5m")
if isinstance(df.columns, pd.MultiIndex):
    df.columns = df.columns.get_level_values(0)

df.index = df.index.tz_convert("Asia/Baghdad")

df['range'] = df['High'] - df['Low']
df['upper_wick'] = df['High'] - df[['Open', 'Close']].max(axis=1)
df['lower_wick'] = df[['Open', 'Close']].min(axis=1) - df['Low']

high_low = df['High'] - df['Low']
high_cp = (df['High'] - df['Close'].shift()).abs()
low_cp = (df['Low'] - df['Close'].shift()).abs()
df['atr'] = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1).rolling(14).mean()

df['ema50'] = df['Close'].ewm(span=50, adjust=False).mean()
df['ema200'] = df['Close'].ewm(span=200, adjust=False).mean()

session_filter = (df.index.hour >= 9) & (df.index.hour <= 19)
liq_bull = (df['lower_wick'] / df['range'] >= 0.50) & (df['range'] >= df['atr'] * 0.7)
liq_bear = (df['upper_wick'] / df['range'] >= 0.50) & (df['range'] >= df['atr'] * 0.7)

trend_bull = (df['Close'] > df['ema50']) & (df['ema50'] > df['ema200'])
trend_bear = (df['Close'] < df['ema50']) & (df['ema50'] < df['ema200'])

setup_bull = session_filter & trend_bull & liq_bull & (df['Close'] > df['Open'])
setup_bear = session_filter & trend_bear & liq_bear & (df['Close'] < df['Open'])

trades = []
rr = 2.0

for i in range(len(df) - 50):
    # شراء: بعد شمعة الرفض، الشمعة التالية تخترق قمتها
    if setup_bull.iloc[i]:
        trigger = df.iloc[i+1]
        if trigger['High'] > df['High'].iloc[i]:
            entry = df['High'].iloc[i]
            sl = df['Low'].iloc[i] - 0.5
            risk = entry - sl
            if 1.5 <= risk <= 6.0:
                tp = entry + (risk * rr)
                be = entry + (risk * 1.0)
                future = df.iloc[i+2:i+45]
                
                be_active = False
                trade_res = None
                for _, bar in future.iterrows():
                    if bar['High'] >= be:
                        be_active = True
                    if bar['High'] >= tp:
                        trade_res = 1
                        break
                    stop_level = entry if be_active else sl
                    if bar['Low'] <= stop_level:
                        trade_res = 0.5 if be_active else 0
                        break
                if trade_res is not None:
                    trades.append(trade_res)

    # بيع: بعد شمعة الرفض، الشمعة التالية تكسر قاعها
    elif setup_bear.iloc[i]:
        trigger = df.iloc[i+1]
        if trigger['Low'] < df['Low'].iloc[i]:
            entry = df['Low'].iloc[i]
            sl = df['High'].iloc[i] + 0.5
            risk = sl - entry
            if 1.5 <= risk <= 6.0:
                tp = entry - (risk * rr)
                be = entry - (risk * 1.0)
                future = df.iloc[i+2:i+45]
                
                be_active = False
                trade_res = None
                for _, bar in future.iterrows():
                    if bar['Low'] <= be:
                        be_active = True
                    if bar['Low'] <= tp:
                        trade_res = 1
                        break
                    stop_level = entry if be_active else sl
                    if bar['High'] >= stop_level:
                        trade_res = 0.5 if be_active else 0
                        break
                if trade_res is not None:
                    trades.append(trade_res)

if trades:
    wins = trades.count(1)
    bes = trades.count(0.5)
    losses = trades.count(0)
    total = len(trades)
    winrate = (wins / total) * 100
    daily_trades = total / 22
    net_r = (wins * rr) - losses
    print("\n===============================")
    print(f"إجمالي الصفقات: {total}")
    print(f"معدل الصفقات اليومي: {daily_trades:.1f} صفقة/يوم")
    print(f"أهداف محققة (TP): {wins} | تأمين خروج بدون خسارة (BE): {bes} | ستوب (SL): {losses}")
    print(f"نسبة الفوز الكامل: {winrate:.1f}%")
    print(f"نسبة عدم الخسارة (Win + BE): {((wins + bes) / total) * 100:.1f}%")
    print(f"صافي العائد: +{net_r:.1f}R")
    print("===============================")
