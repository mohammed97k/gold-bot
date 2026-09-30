import os
import requests
import pandas as pd

# 1. قراءة المفاتيح من إعدادات GitHub (Secrets)
TWELVE_DATA_API_KEY = os.environ.get("TWELVE_DATA_API_KEY")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")           # آيديك الشخصي
TELEGRAM_GROUP_CHAT_ID = os.environ.get("TELEGRAM_GROUP_CHAT_ID") # آيدي القناة

def send_telegram_to_all(message):
    """دالة لإرسال رسالة لكل من الشخص والقناة"""
    # قائمة بالآيديات اللي راح نرسل لها
    chat_ids = []
    if TELEGRAM_CHAT_ID:
        chat_ids.append(TELEGRAM_CHAT_ID)
    if TELEGRAM_GROUP_CHAT_ID:
        chat_ids.append(TELEGRAM_GROUP_CHAT_ID)
    
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message
        }
        try:
            response = requests.post(url, json=payload, timeout=15)
            print(f"Telegram Response for {chat_id}: {response.json()}")
            response.raise_for_status()
            print(f"✅ تم إرسال الرسالة بنجاح إلى {chat_id}")
        except Exception as e:
            print(f"❌ فشل إرسال الرسالة إلى {chat_id}: {e}")

# --- نقطة البداية ---
if __name__ == "__main__":
    print("🤖 بدء تشغيل البوت...")
send_telegram_to_all("ابو الجيس الشغل كلو تمام و مايكل يسلم عليكم")