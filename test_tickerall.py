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

# ============ فتح جلسة ============
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
    if r.status_code == 200:
        account_id = r.json().get("accountId")
        print(f"✅ Account ID: {account_id}")
except Exception as e:
    print(f"❌ Error: {e}")

if not account_id:
    exit()

# ============ جلب شمعات XAUUSD# ============
print("\n" + "=" * 60)
print("📌 جلب شمعات XAUUSD# (M5, 100 شمعة)")
print("=" * 60)

url = f"https://api.tickerall.com/v1/accounts/{account_id}/candles"

# نستخدم timeout طويل جداً (90 ثانية) لأن الـ endpoint بطيء
params = {
    "symbol": "XAUUSD#",
    "timeframe": "M5",
    "limit": 100
}

try:
    print(f"⏳ جاري الطلب... (قد ياخذ حتى 90 ثانية)")
    r = requests.get(url, headers=headers, params=params, timeout=90)
    print(f"Status: {r.status_code}")
    
    if r.status_code == 200:
        data = r.json()
        print(f"\n✅ نجح!")
        print(f"عدد الشمعات: {len(data.get('candles', data.get('bars', data.get('data', []))))}")
        print(f"\nأول 3 شمعات:")
        candles = data.get('candles') or data.get('bars') or data.get('data') or []
        for c in candles[:3]:
            print(f"  {json.dumps(c, ensure_ascii=False)}")
        print(f"\nآخر 3 شمعات:")
        for c in candles[-3:]:
            print(f"  {json.dumps(c, ensure_ascii=False)}")
        print(f"\nكل المفاتيح في الرد: {list(data.keys())}")
    else:
        print(f"Response: {r.text[:1000]}")
except requests.exceptions.ReadTimeout:
    print("⏱️ Read timeout — الـ endpoint موجود بس بطيء جداً")
except Exception as e:
    print(f"❌ Error: {e}")

# ============ تجربة accountId مختلف للـ candles ============
print("\n" + "=" * 60)
print("📌 تجربة endpoints بديلة:")
print("=" * 60)

alt_endpoints = [
    f"/v1/accounts/{account_id}/candles?symbol=XAUUSD%23&timeframe=M5&limit=100",
    f"/v1/market-data/{account_id}/candles?symbol=XAUUSD%23&timeframe=M5&limit=100",
]

for ep in alt_endpoints:
    url = f"https://api.tickerall.com{ep}"
    try:
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 404:
            print(f"\n✅ {ep}")
            print(f"   Status: {r.status_code}")
            print(f"   Response: {r.text[:500]}")
    except Exception as e:
        print(f"⚠️  {ep} -> {e}")

print("\n" + "=" * 60)
print("🏁 انتهى الاختبار")
print("=" * 60)