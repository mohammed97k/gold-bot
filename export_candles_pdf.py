import yfinance as yf
import pandas as pd
import os

os.makedirs("gold_csv_data", exist_ok=True)

# سحب أقصى داتا متصلة تسمح بها خوادم الأسواق المالية
configs = {
    "XAUUSD_Daily": {"symbol": "GC=F", "period": "5y",   "interval": "1d"},
    "XAUUSD_4H":    {"symbol": "GC=F", "period": "2y",   "interval": "1h", "resample": "4h"},
    "XAUUSD_1H":    {"symbol": "GC=F", "period": "2y",   "interval": "1h"},
    "XAUUSD_15M":   {"symbol": "GC=F", "period": "60d",  "interval": "15m"},
    "XAUUSD_5M":    {"symbol": "GC=F", "period": "60d",  "interval": "5m"},
}

for name, cfg in configs.items():
    print(f"Downloading deep continuous data for {name}...")
    df = yf.download(cfg["symbol"], period=cfg["period"], interval=cfg["interval"], progress=False)
    
    if df.empty:
        alt_sym = "XAUUSD=X"
        df = yf.download(alt_sym, period=cfg["period"], interval=cfg["interval"], progress=False)

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    
    df = df.dropna()

    if "resample" in cfg:
        df = df.resample(cfg["resample"]).agg({
            'Open': 'first',
            'High': 'max',
            'Low': 'min',
            'Close': 'last',
            'Volume': 'sum'
        }).dropna()

    # تنسيق الأعمدة المطلوبة للتحليل الكمي
    df = df[['Open', 'High', 'Low', 'Close']]
    df.index.name = 'DateTime'
    
    csv_file = f"gold_csv_data/{name}.csv"
    df.to_csv(csv_file)
    print(f"✓ Saved {len(df)} continuous candles into {csv_file}")

print("\nجميع ملفات الـ CSV التاريخية جاهزة للباك تست المؤسسي!")
