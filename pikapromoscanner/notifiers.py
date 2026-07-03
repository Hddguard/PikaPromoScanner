from __future__ import annotations

import logging
import os

import aiohttp

LOGGER = logging.getLogger("PikaPromoScanner.notifiers")


def telegram_enabled() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and os.getenv("TELEGRAM_CHAT_ID"))


async def send_telegram_alert(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }

    timeout = aiohttp.ClientTimeout(total=20)

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                body = await response.text(errors="replace")
                if response.status >= 400:
                    LOGGER.warning("Telegram alert failed: HTTP %s %s", response.status, body[:500])
                    return False
                return True
    except Exception:
        LOGGER.exception("Telegram alert failed unexpectedly")
        return False
