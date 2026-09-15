import yfinance as yf
import pandas as pd
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
import os
import datetime

timeframes = {
    "Monthly": {"interval": "1mo", "period": "5y"},
    "Weekly":  {"interval": "1wk", "period": "2y"},
    "Daily":   {"interval": "1d",  "period": "1y"},
    "1H":      {"interval": "1h",  "period": "1mo"},
    "30M":     {"interval": "30m", "period": "1mo"},
    "15M":     {"interval": "15m", "period": "1mo"},
    "5M":      {"interval": "5m",  "period": "1mo"},
}

os.makedirs("gold_pdf_candles", exist_ok=True)
styles = getSampleStyleSheet()

tbl_hdr = ParagraphStyle('Hdr', fontName='Helvetica-Bold', fontSize=8, textColor=colors.white, alignment=1)
tbl_cell = ParagraphStyle('Cell', fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#1E293B'), alignment=1)
bull_cell = ParagraphStyle('Bull', fontName='Helvetica-Bold', fontSize=7.5, textColor=colors.HexColor('#166534'), alignment=1)
bear_cell = ParagraphStyle('Bear', fontName='Helvetica-Bold', fontSize=7.5, textColor=colors.HexColor('#991B1B'), alignment=1)

for tf_name, cfg in timeframes.items():
    print(f"جاري سحب شموع فريم {tf_name} وتوليد الـ PDF...")
    df = yf.download("GC=F", period=cfg["period"], interval=cfg["interval"], progress=False)
    if df.empty:
        df = yf.download("XAUUSD=X", period=cfg["period"], interval=cfg["interval"], progress=False)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna()

    # إنشاء ملف الـ PDF
    pdf_path = f"gold_pdf_candles/Gold_{tf_name}_Candles.pdf"
    doc = SimpleDocTemplate(pdf_path, pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    story = [
        Paragraph(f"<b>Gold (XAUUSD) Candlestick Audit - {tf_name}</b>", styles['Title']),
        Paragraph(f"Generated: {datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')} | Total Candles: {len(df)}", styles['Normal']),
        HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#D97706'), spaceBefore=4, spaceAfter=10)
    ]

    # جدول آخر 60 شمعة
    rows = [[Paragraph(h, tbl_hdr) for h in ["Date/Time", "Open", "High", "Low", "Close", "Range", "Type"]]]
    for idx, r in df.tail(60).iterrows():
        dt_str = idx.strftime('%Y-%m-%d %H:%M') if hasattr(idx, 'strftime') else str(idx)[:16]
        c_range = r['High'] - r['Low']
        is_bull = r['Close'] >= r['Open']
        rows.append([
            Paragraph(dt_str, tbl_cell),
            Paragraph(f"${r['Open']:.2f}", tbl_cell),
            Paragraph(f"${r['High']:.2f}", tbl_cell),
            Paragraph(f"${r['Low']:.2f}", tbl_cell),
            Paragraph(f"${r['Close']:.2f}", tbl_cell),
            Paragraph(f"${c_range:.2f}", tbl_cell),
            Paragraph("BULL" if is_bull else "BEAR", bull_cell if is_bull else bear_cell)
        ])

    table = Table(rows, colWidths=[110, 70, 70, 70, 70, 70, 80], repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#0F172A')),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor('#E2E8F0')),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor('#94A3B8')),
        ('TOPPADDING', (0,0), (-1,-1), 3),
        ('BOTTOMPADDING', (0,0), (-1,-1), 3),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F8FAFC')]),
    ]))
    story.append(table)
    doc.build(story)

print("تم توليد جميع ملفات الـ PDF بنجاح في مجلد gold_pdf_candles/!")
