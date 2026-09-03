"""Telegram-Benachrichtigungen via Bot-API. Keine Secrets im Code - siehe config.py."""
from __future__ import annotations

import logging
import time

import requests

from .. import config

logger = logging.getLogger("flight_watcher.telegram")

MAX_RETRIES = 3
TIMEOUT_SECONDS = 15


class TelegramError(Exception):
    pass


def is_configured() -> bool:
    return bool(config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID)


def send_message(text: str) -> bool:
    if not is_configured():
        logger.warning("Telegram nicht konfiguriert (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID fehlen) - übersprungen.")
        return False

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": config.TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": False}

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.post(url, json=payload, timeout=TIMEOUT_SECONDS)
            if resp.status_code == 200:
                return True
            logger.warning("Telegram-API Fehler %s (Versuch %s/%s): %s", resp.status_code, attempt, MAX_RETRIES, resp.text[:200])
            last_error = TelegramError(f"HTTP {resp.status_code}: {resp.text[:200]}")
        except requests.RequestException as exc:
            logger.warning("Telegram Netzwerkfehler (Versuch %s/%s): %s", attempt, MAX_RETRIES, exc)
            last_error = exc
        time.sleep(2 ** attempt)

    logger.error("Telegram-Nachricht konnte nicht gesendet werden: %s", last_error)
    return False
