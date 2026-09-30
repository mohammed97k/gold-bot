import requests

def send_telegram_message(chat_id, message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": chat_id, "text": message}
    try:
        response = requests.post(url, json=payload)
        print(f"Response for {chat_id}: {response.json()}")  # طباعة الرد الكامل
        response.raise_for_status()
        print(f"✅ تم الإرسال إلى {chat_id}")
    except requests.exceptions.HTTPError as e:
        print(f"❌ خطأ HTTP: {e}")
        print(f"رد تيليجرام: {response.text}")  # طباعة نص الرد
    except Exception as e:
        print(f"❌ خطأ آخر: {e}")