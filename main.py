import os
import json
import logging
import secrets
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Request, HTTPException, status
from fastapi.responses import JSONResponse

# =========================
# الإعدادات الأساسية
# =========================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger("tradingview-telegram")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"

app = FastAPI(
    title="TradingView to Telegram Webhook",
    version="1.0.0",
    description="استقبال إشعارات TradingView وإرسالها إلى تليجرام"
)

# =========================
# دوال مساعدة
# =========================
def html_escape(text: Any) -> str:
    """تهريب النصوص لمنع مشاكل HTML في تليجرام"""
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )

def normalize_order_type(order_type: Optional[str]) -> str:
    """توحيد نوع الأمر: Limit => لمت | Market => فوري"""
    if not order_type:
        return "غير محدد"

    ot = str(order_type).strip().lower()

    if ot in ("limit", "lmt", "لمت", "limit order", "limit_order"):
        return "لمت"

    if ot in ("market", "mkt", "فوري", "market order", "market_order"):
        return "فوري"

    return html_escape(order_type)

async def send_telegram_message(text: str) -> None:
    """إرسال الرسالة إلى تليجرام"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.error("Telegram credentials are missing. Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID.")
        return

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(TELEGRAM_API_URL, json=payload)
            response.raise_for_status()
            logger.info("Telegram message sent successfully.")
    except httpx.HTTPStatusError as e:
        logger.error("Telegram API error: %s - %s", e.response.status_code, e.response.text)
    except Exception as e:
        logger.exception("Failed to send Telegram message: %s", e)

def parse_payload(raw_body: bytes, content_type: str) -> dict[str, Any]:
    """يدعم JSON أو نص عادي بصيغة key: value"""
    text = raw_body.decode("utf-8", errors="replace").strip()

    if "application/json" in content_type:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Invalid JSON body, falling back to text parser.")

    # محاولة قراءة JSON حتى لو لم يكن Content-Type صحيحاً
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # نص عادي: symbol: XAUUSD
        data = {}
        for line in text.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                data[key.strip().lower()] = value.strip()
        return data

# =========================
# نقاط النهاية
# =========================
@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

@app.post("/webhook/tradingview")
async def tradingview_webhook(request: Request) -> JSONResponse:
    # 1) التحقق من الأمان
    if WEBHOOK_SECRET:
        provided_secret = (
            request.headers.get("X-TradingView-Secret")
            or request.query_params.get("secret")
        )
        if not provided_secret or not secrets.compare_digest(provided_secret, WEBHOOK_SECRET):
            logger.warning("Unauthorized webhook attempt.")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden"
            )

    # 2) قراءة البيانات
    raw_body = await request.body()
    content_type = request.headers.get("content-type", "")
    payload = parse_payload(raw_body, content_type)
    logger.info("Received webhook payload: %s", payload)

    # 3) استخراج الحقول (يدعم أسماء متعددة)
    def get_field(*names: str) -> Optional[str]:
        for name in names:
            for key, value in payload.items():
                if key.lower() == name.lower():
                    return str(value)
        return None

    symbol = get_field("symbol", "ticker", "pair") or "غير معروف"
    action = get_field("action", "side", "order_action") or "غير معروف"
    order_type_raw = get_field("order_type", "type", "orderType", "نوع_الأمر")
    order_type = normalize_order_type(order_type_raw)
    price = get_field("price", "entry_price", "سعر")
    quantity = get_field("quantity", "qty", "contracts", "volume", "كمية")
    strategy = get_field("strategy", "strategy_name", "اسم_الاستراتيجية") or "استراتيجية غير معروفة"
    timestamp = get_field("time", "timestamp", "timenow", "وقت")

    # 4) تكوين الرسالة
    lines = [
        "🚨 <b>إشعار صفقة جديدة</b>",
        f"<b>الاستراتيجية:</b> {html_escape(strategy)}",
        f"<b>الرمز:</b> {html_escape(symbol)}",
        f"<b>الاتجاه:</b> {html_escape(action)}",
        f"<b>نوع الأمر:</b> {html_escape(order_type)}",
    ]

    if price:
        lines.append(f"<b>السعر:</b> {html_escape(price)}")
    if quantity:
        lines.append(f"<b>الكمية:</b> {html_escape(quantity)}")
    if timestamp:
        lines.append(f"<b>الوقت:</b> {html_escape(timestamp)}")

    message = "\n".join(lines)

    # 5) الإرسال إلى تليجرام
    await send_telegram_message(message)

    return JSONResponse(
        {
            "status": "received",
            "order_type": order_type,
        }
    )

# =========================
# تشغيل مباشر
# =========================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        reload=False
    )