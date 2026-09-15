import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Image as RLImage, PageBreak
import os

timeframes_plan = {
    "Monthly": {"interval": "1mo", "period": "5y",  "pages": 1},
    "Weekly":  {"interval": "1wk", "period": "2y",  "pages": 2},
    "Daily":   {"interval": "1d",  "period": "1y",  "pages": 4},
    "4H":      {"interval": "1h",  "period": "2mo", "pages": 10, "resample": "4h"},
    "1H":      {"interval": "1h",  "period": "2mo", "pages": 15},
    "30M":     {"interval": "30m", "period": "1mo", "pages": 20},
    "15M":     {"interval": "15m", "period": "1mo", "pages": 25},
    "5M":      {"interval": "5m",  "period": "1mo", "pages": 30},
}

os.makedirs("gold_pdf_candles", exist_ok=True)
os.makedirs("temp_pages", exist_ok=True)

CANDLES_PER_PAGE = 15

def render_candlestick_page(df_chunk, page_num, total_pages, tf_name, img_path):
    fig, ax = plt.subplots(figsize=(11.5, 6.2), dpi=180)
    fig.patch.set_facecolor('#080D1A')
    ax.set_facecolor('#080D1A')

    width = 0.58
    wick_width = 2.0

    for i in range(len(df_chunk)):
        row = df_chunk.iloc[i]
        c_open, c_close = row['Open'], row['Close']
        c_high, c_low = row['High'], row['Low']
        is_bull = c_close >= c_open
        color = '#10B981' if is_bull else '#EF4444'

        ax.plot([i, i], [c_low, c_high], color=color, linewidth=wick_width, zorder=2)
        lower = min(c_open, c_close)
        height = max(abs(c_close - c_open), 0.15)
        rect = patches.Rectangle((i - width/2, lower), width, height, facecolor=color, edgecolor=color, zorder=3)
        ax.add_patch(rect)

        ax.text(i, c_high + 0.3, f"{c_high:.1f}", color='#94A3B8', fontsize=6.5, ha='center', va='bottom')
        ax.text(i, c_low - 0.3, f"{c_low:.1f}", color='#94A3B8', fontsize=6.5, ha='center', va='top')

    ax.set_xlim(-0.8, len(df_chunk) - 0.2)
    ax.grid(True, color='#1E293B', linestyle='--', linewidth=0.6, alpha=0.8)
    ax.tick_params(colors='#CBD5E1', labelsize=8.5)

    labels = []
    for idx in df_chunk.index:
        if hasattr(idx, 'strftime'):
            labels.append(idx.strftime('%m/%d %H:%M') if tf_name in ['5M','15M','30M','1H'] else idx.strftime('%Y-%m-%d'))
        else:
            labels.append(str(idx)[:10])

    ax.set_xticks(range(len(df_chunk)))
    ax.set_xticklabels(labels, rotation=20, ha='right', color='#CBD5E1', fontsize=7.5)
    ax.set_ylabel("Price (USD)", color='#CBD5E1', fontsize=10)
    ax.set_title(f"Gold (XAUUSD) - {tf_name} | Page {page_num} of {total_pages} (15 Pure Candlesticks)", 
                 fontsize=12, fontweight='bold', color='#F8FAFC', pad=10)

    plt.tight_layout()
    plt.savefig(img_path, facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close()

for tf_name, cfg in timeframes_plan.items():
    total_candles = cfg["pages"] * CANDLES_PER_PAGE
    print(f"Drawing {total_candles} candles for {tf_name}...")
    
    df = yf.download("GC=F", period=cfg["period"], interval=cfg["interval"], progress=False)
    if df.empty:
        df = yf.download("XAUUSD=X", period=cfg["period"], interval=cfg["interval"], progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()

    if "resample" in cfg:
        df = df.resample('4h').agg({'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last'}).dropna()

    df_selected = df.tail(total_candles).copy()
    pdf_path = f"gold_pdf_candles/Gold_{tf_name}_Candles.pdf"
    doc = SimpleDocTemplate(pdf_path, pagesize=landscape(letter), leftMargin=15, rightMargin=15, topMargin=15, bottomMargin=15)
    story = []

    for p in range(cfg["pages"]):
        chunk = df_selected.iloc[p * CANDLES_PER_PAGE : (p + 1) * CANDLES_PER_PAGE]
        if chunk.empty:
            continue
        img_path = f"temp_pages/{tf_name}_p{p+1}.png"
        render_candlestick_page(chunk, p + 1, cfg["pages"], tf_name, img_path)
        story.append(RLImage(img_path, width=760, height=480))
        if p < cfg["pages"] - 1:
            story.append(PageBreak())

    doc.build(story)
    print(f"Generated {pdf_path}")

print("All visual PDFs successfully generated.")
