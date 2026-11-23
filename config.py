# config.py
INSTRUMENTS = {
    "XAUUSD#": {
        "name": "GOLD",
        "mult": 10.0,       # 1.0 في الشارت = 10 نقاط
        "digits": 2, 
        "divisor": 1.0,
        "min_sl": 40.0, 
        "max_sl": 130.0,
        "tp": [100.0, 200.0, 300.0],  # نقاط الأهداف بناءً على R:R
        "max_dist": 50.0, 
        "buffer": 2.0
    }
}

COOLDOWN_BARS = 10
MAX_BARS_TRADE = 60
EXPIRY_MINUTES = 60
SERVER_OFFSET_HOURS = 3