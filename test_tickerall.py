import os
import requests
import json

API_KEY = os.environ.get("TICKERALL_API_KEY")
MT5_PASSWORD = os.environ.get("MT5_PASSWORD")
MT5_SERVER = os.environ.get("MT5_SERVER")
MT5_ACCOUNT = os.environ.get("MT5_ACCOUNT")

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# قائمة كل الـ endpoints المحتملة
GET_ENDPOINTS = [
    "/",
    "/docs",
    "/openapi.json",
    "/v1",
    "/v1/",
    "/v1/openapi.json",
    "/v1/sessions",
    "/v1/session",
    "/v1/brokers",
    "/v1/broker",
    "/v1/accounts/",
    "/v1/accounts/me",
    "/v1/me",
    "/v1/instruments",
    "/v1/symbols",
    "/v1/market",
    "/v1/market/candles",
    "/v1/quotes",
    "/v1/bars",
    "/v1/history",
    "/v1/data",
    "/v1/ohlc",
    "/v1/positions",
    "/v1/trades",
    "/v1/orders",
]

print("🔍 استكشاف TickerAll API...\n")

for endpoint in GET_ENDPOINTS:
    url = f"https://api.tickerall.com{endpoint}"
    try:
        r = requests.get(url, headers=headers, timeout=8)
        status = r.status_code
        text = r.text[:200].replace("\n", " ")
        # نطبع بس النتائج المهمة
        if status != 404:
            print(f"✅ {endpoint}")
            print(f"   Status: {status}")
            print(f"   Response: {text}")
            print()
        else:
            print(f"❌ {endpoint} (404)")
    except Exception as e:
        print(f"⚠️  {endpoint} -> {e}")

# نجرب POST endpoints
print("\n=== POST endpoints ===\n")
POST_ENDPOINTS = [
    "/v1/sessions",
    "/v1/session",
    "/v1/session/start",
    "/v1/sessions/open",
    "/v1/broker/session",
    "/v1/connect",
    "/v1/sessions/create",
    "/v1/sessions/connect",
    "/v1/accounts/connect",
    "/v1/broker/connect",
]

session_payload = {
    "broker": "mt5",
    "server": MT5_SERVER,
    "account": int(MT5_ACCOUNT) if MT5_ACCOUNT and MT5_ACCOUNT.isdigit() else MT5_ACCOUNT,
    "password": MT5_PASSWORD
}

for endpoint in POST_ENDPOINTS:
    url = f"https://api.tickerall.com{endpoint}"
    try:
        r = requests.post(url, headers=headers, json=session_payload, timeout=10)
        status = r.status_code
        text = r.text[:300].replace("\n", " ")
        if status != 404:
            print(f"✅ {endpoint}")
            print(f"   Status: {status}")
            print(f"   Response: {text}")
            print()
        else:
            print(f"❌ {endpoint} (404)")
    except Exception as e:
        print(f"⚠️  {endpoint} -> {e}")