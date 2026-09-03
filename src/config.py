"""
Zentrale Konfiguration für den Flight Deal Watcher ZRH -> GIG.

Alle Schwellenwerte sind hier gesammelt, damit sie ohne Codeänderung
angepasst werden können. Werte, die Geld/Secrets betreffen, kommen
ausschließlich aus Umgebungsvariablen (.env lokal / GitHub Secrets in
Produktion) - siehe .env.example.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import List, Tuple


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    val = os.environ.get(name)
    return int(val) if val else default


# ---------------------------------------------------------------------------
# Route & Passagiere
# ---------------------------------------------------------------------------
ORIGIN = "ZRH"
DESTINATION = "GIG"
ADULTS = 2
CURRENCY = "CHF"

# ---------------------------------------------------------------------------
# Reiseklasse & Preisgrenzen
# ---------------------------------------------------------------------------
# SerpApi travel_class Codes: 1=Economy, 2=Premium Economy, 3=Business, 4=First
TRAVEL_CLASS = 2  # Premium Economy
TRAVEL_CLASS_NAME = "Premium Economy"

MAX_PRICE_PER_PERSON = 1600  # absolute Obergrenze CHF pro Person
MAX_PRICE_TOTAL = MAX_PRICE_PER_PERSON * ADULTS  # 3'200 CHF für 2 Personen

# Deal-Klassifikation (Grenzen sind INKLUSIVE der oberen Schranke), pro Person in CHF
# Reihenfolge wichtig: von günstig (streng) zu teuer (locker)
DEAL_TIERS: List[Tuple[float, str]] = [
    (1000, "EXTREMER DEAL"),
    (1200, "SEHR STARKER DEAL"),
    (1400, "GUTER DEAL"),
    (1500, "INTERESSANT"),
    (1600, "INNERHALB DER OBERGRENZE"),
]
NO_DEAL_LABEL = "KEIN DEAL-ALARM"

# ---------------------------------------------------------------------------
# Reisedaten (flexible Fenster)
# ---------------------------------------------------------------------------
OUTBOUND_WINDOW = (date(2026, 12, 1), date(2026, 12, 10))
RETURN_WINDOW = (date(2027, 1, 7), date(2027, 1, 15))


def all_date_combinations() -> List[Tuple[date, date]]:
    """Alle sinnvollen Hin-/Rückflug-Kombinationen im Suchfenster."""
    combos = []
    d1, d2 = OUTBOUND_WINDOW
    r1, r2 = RETURN_WINDOW
    outbound_days = (d2 - d1).days + 1
    return_days = (r2 - r1).days + 1
    for i in range(outbound_days):
        out_date = d1 + timedelta(days=i)
        for j in range(return_days):
            ret_date = r1 + timedelta(days=j)
            combos.append((out_date, ret_date))
    return combos


ALL_COMBINATIONS = all_date_combinations()  # z.B. 10 x 9 = 90 Kombinationen

# ---------------------------------------------------------------------------
# Reisezeit & Routing
# ---------------------------------------------------------------------------
MAX_DURATION_MINUTES = 17 * 60  # 17h pro Richtung
MAX_STOPS = 1  # Direktflug oder max. 1 Umstieg
MIN_LAYOVER_MINUTES = 45  # unrealistisch kurze Umsteigezeiten ausschliessen
MAX_LAYOVER_MINUTES = 24 * 60  # > 24h Layover wirkt wie versteckter Stopover, ausschliessen

# ---------------------------------------------------------------------------
# Gepäck
# ---------------------------------------------------------------------------
REQUIRED_CHECKED_BAGS_PER_PERSON = 1

# ---------------------------------------------------------------------------
# API-Budget-Rechnung (SerpApi Google Flights Engine)
# ---------------------------------------------------------------------------
# WICHTIG: Ein bepreister Round-Trip braucht bei SerpApi 2 Calls:
#   1) Outbound-Suche  -> liefert departure_token
#   2) Return-Suche mit departure_token -> liefert den bepreisten Round-Trip
# => REQUESTS_PER_COMBINATION = 2
REQUESTS_PER_COMBINATION = 2
SERPAPI_FREE_TIER_SEARCHES_PER_MONTH = 250

# Sicherheitsmarge einbauen: nicht bis ans Limit ausreizen
SAFETY_MARGIN = 0.9
MONTHLY_SEARCH_BUDGET = int(SERPAPI_FREE_TIER_SEARCHES_PER_MONTH * SAFETY_MARGIN)  # 225
DAILY_COMBINATIONS_TO_CHECK = _env_int("DAILY_COMBINATIONS_TO_CHECK", 4)
DAILY_REQUEST_COST = DAILY_COMBINATIONS_TO_CHECK * REQUESTS_PER_COMBINATION  # 8
MONTHLY_REQUEST_COST = DAILY_REQUEST_COST * 30  # 240 < 225? siehe Warnung unten

# Laufzeit-Warnung, falls die Konfiguration das Budget sprengt (sichtbar in Logs)
BUDGET_OK = MONTHLY_REQUEST_COST <= SERPAPI_FREE_TIER_SEARCHES_PER_MONTH

# ---------------------------------------------------------------------------
# Secrets / externe Dienste (nur aus Umgebungsvariablen!)
# ---------------------------------------------------------------------------
SERPAPI_API_KEY = _env("SERPAPI_API_KEY")

TELEGRAM_BOT_TOKEN = _env("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = _env("TELEGRAM_CHAT_ID")

SMTP_HOST = _env("SMTP_HOST")
SMTP_PORT = _env_int("SMTP_PORT", 587)
SMTP_USER = _env("SMTP_USER")
SMTP_PASSWORD = _env("SMTP_PASSWORD")
EMAIL_FROM = _env("EMAIL_FROM")
EMAIL_TO = _env("EMAIL_TO")

# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------
DB_PATH = _env("DB_PATH", "data/flights.db")

# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
DASHBOARD_OUTPUT_PATH = _env("DASHBOARD_OUTPUT_PATH", "docs/index.html")
TOP_DEALS_COUNT = 10


@dataclass
class RuntimeFlags:
    dry_run: bool = False
    test_telegram: bool = False
    test_email: bool = False
