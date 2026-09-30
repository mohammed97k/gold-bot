import os
import requests

# قراءة المفاتيح
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

print("🤖 بدء اختبار التيليجرام...")
print(f"التوكن موجود: {'نعم' if TELEGRAM_BOT_TOKEN else 'لا'}")
print(f"الآيدي موجود: {'نعم' if TELEGRAM_CHAT_ID else 'لا'}")

if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": "🚀 رسالة اختبار من GitHub Actions!"
    }
    try:
        response = requests.post(url, json=payload, timeout=15) # ضفنا timeout
        print(f"رد تيليجرام: {response.json()}")
        response.raise_for_status()
        print("✅ تم الإرسال بنجاح!")
    except Exception as e:
        print(f"❌ فشل: {e}")
else:
    print("❌ ناقص التوكن أو الآيدي!")