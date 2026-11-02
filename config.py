# config.py
# إعدادات الأزواج والنماذج المستخرجة من الاستراتيجية الجديدة

INSTRUMENTS = {
    "XAUUSD#": {
        "name": "GOLD",
        "profile": "gold",
        "mult": 10,             
        "digits": 2,            # عدد الخانات العشرية
        "divisor": 1.0,         # قاسم تصحيح السعر (لا يحتاج تعديل)
        "min_sl": 40.0,
        "max_sl": 130.0,
        "buffer": 10.0,         
        "tp": [100.0, 200.0, 300.0],
        "max_dist": 40.0,       
        "allowed_models": [
            "IOFED", "FVG-Direct", "OB-Pro", "SMR", "Mitigation", 
            "MMBM", "2022", "Reaper", "SBPM-MSS", "Judas", "TGIF"
        ]
    },
    "NDXUSD#": {
        "name": "NAS100",
        "profile": "indices",
        "mult": 1,              
        "digits": 2,
        "divisor": 1.0,
        "min_sl": 40.0,
        "max_sl": 150.0,
        "buffer": 10.0,
        "tp": [100.0, 200.0, 300.0],
        "max_dist": 40.0,
        "allowed_models": ["Mitigation", "SMR", "OB-Pro", "MMBM", "FVG-Direct"]
    },
    "DJIUSD#": {
        "name": "US30",
        "profile": "indices",
        "mult": 1,
        "digits": 2,
        "divisor": 1.0,
        "min_sl": 40.0,
        "max_sl": 150.0,
        "buffer": 10.0,
        "tp": [100.0, 200.0, 300.0],
        "max_dist": 40.0,
        "allowed_models": ["Mitigation", "SMR", "OB-Pro", "MMBM", "FVG-Direct"]
    },
    "EURJPY#": {
        "name": "EURJPY",
        "profile": "forex",
        "mult": 100,            
        "digits": 3,            # الين يحتاج 3 خانات
        "divisor": 10.0,        # تصحيح السعر
        "min_sl": 8.0,
        "max_sl": 20.0,
        "buffer": 2.0,
        "tp": [20.0, 30.0, 40.0],
        "max_dist": 8.0,
        "allowed_models": ["FVG-Direct", "SMR"]
    },
    "GBPJPY#": {
        "name": "GBPJPY",
        "profile": "forex",
        "mult": 100,
        "digits": 3,            # الين يحتاج 3 خانات
        "divisor": 10.0,        # تصحيح السعر
        "min_sl": 8.0,
        "max_sl": 20.0,
        "buffer": 2.0,
        "tp": [20.0, 30.0, 40.0],
        "max_dist": 8.0,
        "allowed_models": ["IOFED", "OB-Pro", "SMR", "Mitigation", "MMBM"]
    }
}

# إعدادات عامة
COOLDOWN_BARS = 10
MAX_BARS_TRADE = 60
EXPIRY_MINUTES = 60
SERVER_OFFSET_HOURS = 3