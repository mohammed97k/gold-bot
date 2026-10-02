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

# ============ فتح جلسة أولاً ============
print("=" * 60)
print("📌 فتح جلسة MT5...")
print("=" * 60)

session_payload = {
    "broker": "mt5",
    "server": MT5_SERVER,
    "account": int(MT5_ACCOUNT) if MT5_ACCOUNT and MT5_ACCOUNT.isdigit() else MT5_ACCOUNT,
    "password": MT5_PASSWORD
}

account_id = None
try:
    r = requests.post("https://api.tickerall.com/v1/sessions",
                      headers=headers, json=session_payload, timeout=25)
    print(f"Status: {r.status_code}")
    print(f"Response: {json.dumps(r.json(), indent=2, ensure_ascii=False)}")
    if r.status_code == 200:
        account_id = r.json().get("accountId")
        print(f"\n✅ Account ID: {account_id}")
except Exception as e:
    print(f"❌ Error: {e}")

if not account_id:
    print("❌ ما نقدر نكمل بدون Account ID")
    exit()

# ============ استكشاف endpoints مع accountId ============
print("\n" + "=" * 60)
print(f"🔍 استكشاف endpoints مع accountId = {account_id}")
print("=" * 60)

GET_ENDPOINTS = [
    f"/v1/accounts/{account_id}",
    f"/v1/accounts/{account_id}/",
    f"/v1/accounts/{account_id}/candles",
    f"/v1/accounts/{account_id}/bars",
    f"/v1/accounts/{account_id}/ohlc",
    f"/v1/accounts/{account_id}/quotes",
    f"/v1/accounts/{account_id}/symbols",
    f"/v1/accounts/{account_id}/instruments",
    f"/v1/accounts/{account_id}/market-data",
    f"/v1/accounts/{account_id}/prices",
    f"/v1/accounts/{account_id}/tick",
    f"/v1/accounts/{account_id}/history",
    f"/v1/accounts/{account_id}/positions",
    f"/v1/accounts/{account_id}/info",
    f"/v1/market-data/{account_id}",
    f"/v1/market-data/{account_id}/candles",
    f"/v1/marketdata/{account_id}",
    f"/v1/md/{account_id}",
    f"/v1/md/{account_id}/candles",
    f"/v1/sessions/{account_id}",
    f"/v1/sessions/{account_id}/candles",
    f"/v1/data/{account_id}",
    f"/v1/candles/{account_id}",
    f"/v1/bars/{account_id}",
]

for endpoint in GET_ENDPOINTS:
    url = f"https://api.tickerall.com{endpoint}"
    try:
        r = requests.get(url, headers=headers,
                         params={"symbol": "XAUUSD", "timeframe": "M5", "limit": 5},
                         timeout=8)
        status = r.status_code
        if status != 404:
            print(f"\n✅ {endpoint}")
            print(f"   Status: {status}")
            print(f"   Response: {r.text[:600]}")
        else:
            print(f"❌ {endpoint}")
    except Exception as e:
        print(f"⚠️  {endpoint} -> {e}")