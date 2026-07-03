from __future__ import annotations

import logging
import os

import aiohttp

LOGGER = logging.getLogger("PikaPromoScanner.notifiers")


def telegram_chat_ids() -> list[str]:
    multi = os.getenv("TELEGRAM_CHAT_IDS", "").strip()
    single = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    raw = multi or single
    if not raw:
        return []

    return [chat_id.strip() for chat_id in raw.split(",") if chat_id.strip()]


def telegram_enabled() -> bool:
    return bool(os.getenv("TELEGRAM_BOT_TOKEN") and telegram_chat_ids())


async def send_telegram_alert(text: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_ids = telegram_chat_ids()

    if not token or not chat_ids:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"

    timeout = aiohttp.ClientTimeout(total=20)
    sent_any = False

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for chat_id in chat_ids:
                payload = {
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": False,
                }

                async with session.post(url, json=payload) as response:
                    body = await response.text(errors="replace")
                    if response.status >= 400:
                        LOGGER.warning(
                            "Telegram alert failed for chat_id %s: HTTP %s %s",
                            chat_id,
                            response.status,
                            body[:500],
                        )
                        continue

                    sent_any = True

        return sent_any

    except Exception:
        LOGGER.exception("Telegram alert failed unexpectedly")
        return False
