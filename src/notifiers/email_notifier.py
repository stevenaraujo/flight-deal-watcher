"""
E-Mail-Benachrichtigungen via SMTP.

Bewusst SMTP statt eines weiteren Drittanbieter-Dienstes gewählt:
- funktioniert kostenlos z.B. mit einem Gmail-Konto + App-Passwort
  (kein normales Passwort, kein Klartext-Login, jederzeit widerrufbar)
- keine zusätzliche Abhängigkeit/Kosten
- Zugangsdaten kommen ausschliesslich aus GitHub Secrets / .env
"""
from __future__ import annotations

import logging
import smtplib
import time
from email.mime.text import MIMEText

from .. import config

logger = logging.getLogger("flight_watcher.email")

MAX_RETRIES = 3


class EmailError(Exception):
    pass


def is_configured() -> bool:
    return bool(config.SMTP_HOST and config.SMTP_USER and config.SMTP_PASSWORD and config.EMAIL_FROM and config.EMAIL_TO)


def send_email(subject: str, body: str) -> bool:
    if not is_configured():
        logger.warning("E-Mail nicht konfiguriert (SMTP_*/EMAIL_* fehlen) - übersprungen.")
        return False

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_FROM
    msg["To"] = config.EMAIL_TO

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=20) as server:
                server.starttls()
                server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.sendmail(config.EMAIL_FROM, [config.EMAIL_TO], msg.as_string())
            return True
        except smtplib.SMTPException as exc:
            logger.warning("SMTP-Fehler (Versuch %s/%s): %s", attempt, MAX_RETRIES, exc)
            last_error = exc
        except OSError as exc:
            logger.warning("E-Mail Netzwerkfehler (Versuch %s/%s): %s", attempt, MAX_RETRIES, exc)
            last_error = exc
        time.sleep(2 ** attempt)

    logger.error("E-Mail konnte nicht gesendet werden: %s", last_error)
    return False
