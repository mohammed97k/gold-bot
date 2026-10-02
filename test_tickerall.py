import os
import requests

API_KEY = os.environ.get("TICKERALL_API_KEY")
MT5_PASSWORD = os.environ.get("MT5_PASSWORD")
MT5_SERVER = os.environ.get("MT5_SERVER")
MT5_ACCOUNT = os.environ.get("MT5_ACCOUNT")

print("🔍 اختبار TickerAll API...")
print(f"API Key موجود: {'نعم' if API_KEY else 'لا'}")
print(f"MT5 Password موجود: {'نعم' if MT5_PASSWORD else 'لا'}")
print(f"Server: {MT5_SERVER}")
print(f"Account: {MT5_ACCOUNT}")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# اختبار 1: الاتصال الأساسي
print("\n=== اختبار 1: الاتصال الأساسي ===")
try:
    r = requests.get("https://api.tickerall.com/v1/accounts", headers=headers, timeout=15)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:800]}")
except Exception as e:
    print(f"Error: {e}")

# اختبار 2: فتح جلسة MT5
print("\n=== اختبار 2: فتح جلسة MT5 ===")
session_payload = {
    "broker": "mt5",
    "server": MT5_SERVER,
    "account": int(MT5_ACCOUNT) if MT5_ACCOUNT and MT5_ACCOUNT.isdigit() else MT5_ACCOUNT,
    "password": MT5_PASSWORD
}
try:
    r = requests.post("https://api.tickerall.com/v1/sessions/start",
                      headers=headers, json=session_payload, timeout=20)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:1000]}")
except Exception as e:
    print(f"Error: {e}")

# اختبار 3: جلب شمعات XAUUSD
print("\n=== اختبار 3: جلب شمعات XAUUSD ===")
try:
    r = requests.get("https://api.tickerall.com/v1/candles",
                     headers=headers,
                     params={"symbol": "XAUUSD", "timeframe": "M5", "limit": 5},
                     timeout=15)
    print(f"Status: {r.status_code}")
    print(f"Response: {r.text[:1000]}")
except Exception as e:
    print(f"Error: {e}")