def notify_entry(
    order_type: str,
    direction: str,
    entry_price: float,
    sl: float,
    tp: float,
    time_str: str,
):
    """
    order_type: 'فوري (MARKET)' أو 'معلّق (LIMIT)'
    direction: 'شراء' أو 'بيع'
    """
    icon = "🟢" if "شراء" in direction or "BUY" in direction else "🔴"
    sl_pts = abs(entry_price - sl) / 0.10
    tp_pts = abs(tp - entry_price) / 0.10

    msg = (
        f"⚡ *إشارة MSNR جديدة (XAUUSD)*\n\n"
        f"▫️ *طبيعة الدخول:* `{order_type}`\n"
        f"▫️ *الاتجاه:* {direction} {icon}\n"
        f"▫️ *سعر الدخول:* `{entry_price:.2f}`\n"
        f"▫️ *وقف الخسارة (SL):* `{sl:.2f}` ({sl_pts:.0f} نقطة)\n"
        f"▫️ *الهدف (TP):* `{tp:.2f}` ({tp_pts:.0f} نقطة)\n"
        f"▫️ *نسبة العائد R:R:* 1:1.8\n"
        f"▫️ *الوقت:* `{time_str}`"
    )
    send_telegram(msg)
