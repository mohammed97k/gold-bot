import os
import requests
import pandas as pd
from datetime import datetime
import pytz

# 1. قراءة المفاتيح من إعدادات GitHub (Secrets)
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    """دالة لإرسال رسالة على تيليجرام"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("✅ تم إرسال رسالة التيليجرام بنجاح")
    except Exception as e:
        print(f"❌ فشل إرسال رسالة التيليجرام: {e}")

def fetch_gold_data():
    """دالة لجلب بيانات الذهب من Twelve Data"""
    print("⏳ جاري جلب البيانات من Twelve Data...")
    
    # رابط الـ API لجلب شمعات 5 دقائق للذهب
    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": "XAU/USD",
        "interval": "5min",
        "outputsize": 500, # نجلب 500 شمعة كبداية
        "apikey": TWELVE_DATA_API_KEY,
        "format": "JSON"
    }
    
    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        # التحقق من وجود خطأ في الاستجابة
        if "code" in data and data["code"] != 200:
            error_msg = data.get("message", "خطأ غير معروف")
            print(f"❌ فشل جلب البيانات: {error_msg}")
            return None
            
        if "values" not in data:
            print("❌ لا توجد بيانات في الاستجابة")
            return None
            
        # تحويل البيانات إلى DataFrame
        df = pd.DataFrame(data["values"])
        
        # تحويل الأعمدة إلى أرقام وتواريخ
        df["datetime"] = pd.to_datetime(df["datetime"])
        for col in ["open", "high", "low", "close"]:
            df[col] = pd.to_numeric(df[col])
            
        # ترتيب البيانات من الأقدم إلى الأحدث (لأن API يرجعها بالعكس)
        df = df.sort_values("datetime").reset_index(drop=True)
        
        print(f"✅ تم جلب {len(df)} شمعة بنجاح.")
        print(f"آخر شمعة: {df.iloc[-1]['datetime']} | السعر: {df.iloc[-1]['close']}")
        
        return df
        
    except Exception as e:
        print(f"❌ حدث خطأ أثناء جلب البيانات: {e}")
        return None

# --- نقطة البداية ---
if __name__ == "__main__":
    print("🤖 بدء تشغيل البوت...")
    
    # اختبار إرسال رسالة تيليجرام
    send_telegram_message("🤖 البوت اشتغل! جاري اختبار جلب البيانات من Twelve Data...")
    
    # جلب البيانات
    df = fetch_gold_data()
    
    if df is not None:
        send_telegram_message(f"✅ تم الاتصال بـ Twelve Data بنجاح!\nسعر الذهب الحالي: {df.iloc[-1]['close']}")
    else:
        send_telegram_message("❌ فشل الاتصال بـ Twelve Data. يرجى مراجعة المفتاح أو الاتصال.")