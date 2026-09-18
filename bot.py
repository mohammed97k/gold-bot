import os
import sys
import requests
import yfinance as yf
import pandas as pd
import numpy as np

# 1. إعدادات التليجرام
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()

def send_telegram(text: str):
    """إرسال الإشعار لتليجرام"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[!] خطأ: التوكن أو الآيدي غير موجود في متغيرات البيئة.")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[!] خطأ في الاتصال بتليجرام: {e}")
        return False

def notify_entry(order_type: str, direction: str, entry_price: float, sl: float, tp: float, time_str: str):
    """تنسيق وإرسال إشعار الصفقة"""
    icon = "🟢" if "شراء" in direction or "BUY" in direction else "🔴"
    sl_pts = abs(entry_price - sl) / 0.10
    tp_pts = abs(tp - entry_price) / 0.10
    
    msg = (
        f"⚡ *إشارة MSNR جديدة (XAUUSD)*\n\n"
        f"▫️ *طبيعة الدخول:* `{order_type}`\n"
        f"▫️ *الاتجاه:* {direction} {icon}\n"
        f"▫️ *سعر الدخول:* `{entry_price:.2f}`\n"
        f"▫️ *وقف الخسارة (SL):* `{sl:.2f}` ({sl_pts:.0f} نقطة)\n"
        f"▫️ *الهدف (TP):* `{tp:.2f}` ({tp_pts:.0f} نقطة)\n"
        f"▫️ *نسبة العائد R:R:* 1:1.8\n"
        f"▫️ *الوقت:* `{time_str}`"
    )
    send_telegram(msg)

# 2. محرك فحص الشموع وتوليد الإشارات الحية
def analyze_gold_market():
    print("[*] جلب شموع الذهب من السوق...")
    ticker = yf.Ticker("GC=F")
    df = ticker.history(period="5d", interval="15m")
    
    if df.empty or len(df) < 30:
        print("[!] تعذر جلب البيانات أو البيانات غير كافية.")
        return

    df = df.reset_index()
    df.rename(columns={
        "Datetime": "time", "Date": "time", 
        "Open": "open", "High": "high", "Low": "low", "Close": "close"
    }, inplace=True)

    lookback = 10
    rr_ratio = 1.8

    # استخراج القمم والقيعان الهيكلية
    df['p_high'] = df['high'].shift(1).rolling(lookback).max()
    df['p_low']  = df['low'].shift(1).rolling(lookback).min()

    res_level = None
    sup_level = None
    res_broken = False
    sup_broken = False

    for i in range(len(df) - 15, len(df)):
        row = df.iloc[i]
        
        if pd.notna(row['p_high']):
            res_level = row['p_high']
            res_broken = False
        if pd.notna(row['p_low']):
            sup_level = row['p_low']
            sup_broken = False

        if res_level and not res_broken and row['close'] > res_level:
            res_broken = True
        if sup_level and not sup_broken and row['close'] < sup_level:
            sup_broken = True

        if i == len(df) - 1:
            t_str = str(row['time'])[:16]

            # شرط الشراء
            if res_broken and (row['low'] <= res_level) and (row['close'] >= res_level) and (row['close'] > row['open']):
                is_limit = abs(row['close'] - res_level) > 0.40
                order_t = "شراء معلّق (BUY LIMIT)" if is_limit else "شراء فوري (BUY MARKET)"
                entry_p = res_level if is_limit else row['close']
                
                raw_dist = abs(row['close'] - min(row['low'], res_level)) + 0.50
                sl_dist = max(5.0, min(13.0, raw_dist))
                tp_dist = max(10.0, min(25.0, sl_dist * rr_ratio))
                
                notify_entry(order_t, "شراء (BUY)", entry_p, entry_p - sl_dist, entry_p + tp_dist, t_str)
                print(f"[+] تم إرسال صفقة شراء: {entry_p}")
                return

            # شرط البيع
            elif sup_broken and (row['high'] >= sup_level) and (row['close'] <= sup_level) and (row['close'] < row['open']):
                is_limit = abs(row['close'] - sup_level) > 0.40
                order_t = "بيع معلّق (SELL LIMIT)" if is_limit else "بيع فوري (SELL MARKET)"
                entry_p = sup_level if is_limit else row['close']
                
                raw_dist = abs(max(row['high'], sup_level) - row['close']) + 0.50
                sl_dist = max(5.0, min(13.0, raw_dist))
                tp_dist = max(10.0, min(25.0, sl_dist * rr_ratio))
                
                notify_entry(order_t, "بيع (SELL)", entry_p, entry_p + sl_dist, entry_p - tp_dist, t_str)
                print(f"[+] تم إرسال صفقة بيع: {entry_p}")
                return

    print("[-] لا توجد إشارة دخول جديدة متحققة على الشمعة الحالية.")

if __name__ == "__main__":
    print("[*] بدء تشغيل البوت...")
    analyze_gold_market()
