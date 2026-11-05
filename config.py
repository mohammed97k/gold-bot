# config.py
# الإعدادات المطابقة لاستراتيجية ICT Ultimate Multi-Symbol Master (v6)

INSTRUMENTS = {
    "XAUUSD#": {
        "name": "GOLD",
        "mult": 10.0, 
        "digits": 2, 
        "divisor": 1.0,
        "min_sl": 40.0, "max_sl": 130.0,
        "tp": [100.0, 200.0, 300.0],
        "max_dist": 40.0, 
        "buffer": 2.0,
        "allowed_models": [
            "M16: Immed Rebal", "M53: Risk Gov", "M76: Disrespect BISI", "M26: Ma Deuce", 
            "M6: Propulsion", "M64: Morning Macro", "M18: Rejection", "M56: Zerocon", 
            "M68: FVG Quadrants", "M11: Unicorn", "M46: Lawnmower", "M97: BPR", 
            "M45: 10-Min Rule", "M17: Mitigation", "M54: Algo Clock", "M50: Key Turn Pt", 
            "M59: Second Redist", "M79: Index Precision", "M103: 15m Fractal", "M106: BPR Bolo"
        ]
    },
    "NDXUSD#": {
        "name": "NAS100",
        "mult": 1.0,
        "digits": 2, 
        "divisor": 1.0,
        "min_sl": 40.0, "max_sl": 150.0,
        "tp": [100.0, 200.0, 300.0],
        "max_dist": 40.0, 
        "buffer": 2.0,
        "allowed_models": [
            "M1: ICT 2022", "M4: MMSM", "M13: FOMC 2-Stage", "M16: Immed Rebal", 
            "M17: Mitigation", "M41: Old Highs", "M45: 10-Min Rule", "M53: Risk Gov", 
            "M55: Master Check", "M61: IPDA 60-Day", "M64: Morning Macro", "M76: Disrespect BISI", 
            "M92: Real Void", "M99: Old Highs/Lows", "M102: Full Replic", "M111: IPDA 60D", "M114: Morning Macro"
        ]
    },
    "DJIUSD#": {
        "name": "US30",
        "mult": 1.0,
        "digits": 2, 
        "divisor": 1.0,
        "min_sl": 40.0, "max_sl": 150.0,
        "tp": [100.0, 200.0, 300.0],
        "max_dist": 40.0, 
        "buffer": 2.0,
        "allowed_models": [
            "M6: Propulsion", "M11: Unicorn", "M16: Immed Rebal", "M17: Mitigation", 
            "M45: 10-Min Rule", "M46: Lawnmower", "M50: Key Turn Pt", "M56: Zerocon", 
            "M64: Morning Macro", "M68: FVG Quad", "M76: Disrespect BISI", "M97: BPR", 
            "M104: Early Focus", "M106: BPR Bolo"
        ]
    },
    "GBPJPY#": {
        "name": "GBPJPY",
        "mult": 100.0, 
        "digits": 3, 
        "divisor": 10.0,
        "min_sl": 8.0, "max_sl": 20.0,
        "tp": [20.0, 30.0, 40.0],
        "max_dist": 8.0, 
        "buffer": 2.0,
        "allowed_models": [
            "M6: Propulsion", "M10: Judas Swing", "M13: FOMC 2-Stage", 
            "M16: Immed Rebal", "M45: 10-Min Rule", "M75: Pre-Open Trap", "M76: Disrespect BISI"
        ]
    },
    "EURUSD#": {
        "name": "EURUSD",
        "mult": 10000.0, 
        "digits": 5, 
        "divisor": 1.0,
        "min_sl": 8.0, "max_sl": 20.0,
        "tp": [20.0, 30.0, 40.0],
        "max_dist": 8.0, 
        "buffer": 2.0,
        "allowed_models": ["M2: Silver Bullet", "M16: Immed Rebal", "M76: Disrespect"]
    },
    "GBPUSD#": {
        "name": "GBPUSD",
        "mult": 10000.0, 
        "digits": 5, 
        "divisor": 1.0,
        "min_sl": 8.0, "max_sl": 20.0,
        "tp": [20.0, 30.0, 40.0],
        "max_dist": 8.0, 
        "buffer": 2.0,
        "allowed_models": ["M16: Immed Rebal", "M42: Q-Shift", "M76: Disrespect BISI"]
    },
    "EURJPY#": {
        "name": "EURJPY",
        "mult": 100.0, 
        "digits": 3, 
        "divisor": 10.0,
        "min_sl": 8.0, "max_sl": 20.0,
        "tp": [20.0, 30.0, 40.0],
        "max_dist": 8.0, 
        "buffer": 2.0,
        "allowed_models": ["M16: Immed Rebal", "M43: Anti-Revenge", "M13: FOMC 2-Stage", "M32: Sympathy", "M57: Reaper"]
    },
    "USDCHF#": {
        "name": "USDCHF",
        "mult": 10000.0, 
        "digits": 5, 
        "divisor": 1.0,
        "min_sl": 8.0, "max_sl": 20.0,
        "tp": [20.0, 30.0, 40.0],
        "max_dist": 8.0, 
        "buffer": 2.0,
        "allowed_models": ["M16: Immed Rebal", "M31: Seek/Destroy", "M76: Disrespect BISI"]
    }
}

COOLDOWN_BARS = 50 
MAX_BARS_TRADE = 60
EXPIRY_MINUTES = 60
SERVER_OFFSET_HOURS = 3