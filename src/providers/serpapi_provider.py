"""
Provider-Modul für die SerpApi Google-Flights-Engine.

Verantwortlich für:
- HTTP-Requests an SerpApi (mit Retry/Backoff/Timeout)
- Umwandlung der rohen JSON-Antwort in normalisierte FlightOffer-Objekte

Kein anderes Modul darf SerpApi-spezifische JSON-Felder kennen -
alles Provider-Spezifische bleibt hier gekapselt (Austauschbarkeit).
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import requests

from .. import config
from ..models import BaggageInfo, FlightLeg, FlightOffer

logger = logging.getLogger("flight_watcher.serpapi")

BASE_URL = "https://serpapi.com/search"
TIMEOUT_SECONDS = 20
MAX_RETRIES = 3
BACKOFF_BASE_SECONDS = 2


class ProviderError(Exception):
    """Wird geworfen, wenn der Provider dauerhaft nicht antwortet / Fehler liefert."""


class RateLimitError(ProviderError):
    pass


class InvalidApiKeyError(ProviderError):
    pass


def _request(params: Dict[str, Any]) -> Dict[str, Any]:
    """Führt einen SerpApi-Request mit Retry/Backoff aus."""
    if not config.SERPAPI_API_KEY:
        raise InvalidApiKeyError("SERPAPI_API_KEY ist nicht gesetzt.")

    params = {**params, "api_key": config.SERPAPI_API_KEY}
    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            last_error = exc
            logger.warning("SerpApi Netzwerkfehler (Versuch %s/%s): %s", attempt, MAX_RETRIES, exc)
            time.sleep(BACKOFF_BASE_SECONDS ** attempt)
            continue

        if resp.status_code == 401:
            raise InvalidApiKeyError(f"SerpApi lehnt den API-Key ab: {resp.text[:200]}")
        if resp.status_code == 429:
            logger.warning("SerpApi Rate-Limit erreicht (Versuch %s/%s)", attempt, MAX_RETRIES)
            time.sleep(BACKOFF_BASE_SECONDS ** attempt)
            last_error = RateLimitError("SerpApi Rate-Limit (429)")
            continue
        if resp.status_code >= 500:
            logger.warning("SerpApi Server-Fehler %s (Versuch %s/%s)", resp.status_code, attempt, MAX_RETRIES)
            time.sleep(BACKOFF_BASE_SECONDS ** attempt)
            last_error = ProviderError(f"SerpApi 5xx: {resp.status_code}")
            continue
        if resp.status_code != 200:
            raise ProviderError(f"SerpApi unerwarteter Status {resp.status_code}: {resp.text[:200]}")

        data = resp.json()
        if data.get("error"):
            raise ProviderError(f"SerpApi Fehler im Payload: {data['error']}")
        return data

    raise last_error or ProviderError("SerpApi: Alle Retries fehlgeschlagen.")


def search_round_trip(outbound_date: date, return_date: date) -> List[FlightOffer]:
    """
    Sucht ein Round-Trip-Angebot für ein Datumspaar.

    Ablauf (2 API-Calls, siehe config.REQUESTS_PER_COMBINATION):
      1. Outbound-Suche -> beste(s) departure_token(s)
      2. Return-Suche mit departure_token -> bepreiste Round-Trips
    """
    search_params = {
        "engine": "google_flights",
        "departure_id": config.ORIGIN,
        "arrival_id": config.DESTINATION,
        "outbound_date": outbound_date.isoformat(),
        "return_date": return_date.isoformat(),
        "travel_class": config.TRAVEL_CLASS,
        "adults": config.ADULTS,
        "currency": config.CURRENCY,
        "type": 1,  # Round trip
        "stops": 1 if config.MAX_STOPS <= 1 else 0,  # 1 = "Nonstop or 1 stop" Filter bei Google Flights
    }

    outbound_data = _request(search_params)
    best_flights = outbound_data.get("best_flights", []) or outbound_data.get("other_flights", [])
    if not best_flights:
        logger.info("Keine Outbound-Ergebnisse für %s -> %s", outbound_date, return_date)
        return []

    top_option = best_flights[0]
    departure_token = top_option.get("departure_token")
    if not departure_token:
        logger.warning("Kein departure_token erhalten für %s -> %s", outbound_date, return_date)
        return []

    return_params = {**search_params, "departure_token": departure_token}
    priced_data = _request(return_params)

    offers: List[FlightOffer] = []
    for candidate in (priced_data.get("best_flights", []) or []) + (priced_data.get("other_flights", []) or []):
        offer = _normalize_offer(candidate, outbound_date, return_date, priced_data)
        if offer:
            offers.append(offer)
    return offers


def _parse_dt(raw: str) -> datetime:
    # SerpApi liefert z.B. "2026-12-03 08:15"
    return datetime.strptime(raw, "%Y-%m-%d %H:%M")


def _extract_legs(raw_flights: List[Dict[str, Any]]) -> List[FlightLeg]:
    legs = []
    for f in raw_flights:
        legs.append(
            FlightLeg(
                airline=f.get("airline", "unbekannt"),
                flight_number=f.get("flight_number", ""),
                departure_airport=f.get("departure_airport", {}).get("id", ""),
                arrival_airport=f.get("arrival_airport", {}).get("id", ""),
                departure_time=_parse_dt(f["departure_airport"]["time"]),
                arrival_time=_parse_dt(f["arrival_airport"]["time"]),
                duration_minutes=f.get("duration", 0),
                travel_class=f.get("travel_class", config.TRAVEL_CLASS_NAME),
            )
        )
    return legs


def _layovers_minutes(raw_layovers: List[Dict[str, Any]]) -> List[int]:
    return [lay.get("duration", 0) for lay in raw_layovers or []]


def _detect_self_transfer(raw_layovers: List[Dict[str, Any]]) -> bool:
    for lay in raw_layovers or []:
        if lay.get("overnight") or lay.get("airport_change"):
            return True
    return False


def _extract_baggage(candidate: Dict[str, Any], priced_data: Dict[str, Any]) -> BaggageInfo:
    baggage_prices = priced_data.get("baggage_prices") or candidate.get("baggage_prices")
    if not baggage_prices:
        return BaggageInfo(checked_bags_included=0, verified=False)

    # Grobe Heuristik über den von SerpApi gelieferten Freitext, da das Feld nicht
    # vollständig strukturiert ist. Konservativ: nur als "included" werten, wenn
    # ausdrücklich von inkludiertem Gepäck die Rede ist.
    text = " ".join(str(x) for x in baggage_prices).lower()
    if "1st checked bag" in text and "free" in text:
        return BaggageInfo(checked_bags_included=1, verified=True)
    if "included" in text:
        return BaggageInfo(checked_bags_included=1, verified=True)
    return BaggageInfo(checked_bags_included=0, verified=True, extra_bag_cost_per_person=None)


def _extract_booking_link(priced_data: Dict[str, Any]) -> Optional[str]:
    options = priced_data.get("booking_options") or []
    for opt in options:
        book_with = opt.get("together") or opt.get("departing")
        if book_with and book_with.get("booking_request"):
            return book_with["booking_request"].get("url")
    search_metadata = priced_data.get("search_metadata", {})
    return search_metadata.get("google_flights_url")


def _normalize_offer(
    candidate: Dict[str, Any],
    outbound_date: date,
    return_date: date,
    priced_data: Dict[str, Any],
) -> Optional[FlightOffer]:
    try:
        flights = candidate.get("flights", [])
        layovers = candidate.get("layovers", [])
        if not flights:
            return None

        # Google Flights liefert Outbound+Return oft als eine kombinierte Liste;
        # wir trennen anhand des Datumswechsels (grobe, robuste Heuristik).
        outbound_legs_raw = [f for f in flights if _parse_dt(f["departure_airport"]["time"]).date() <= outbound_date + config_max_slip()]
        return_legs_raw = [f for f in flights if f not in outbound_legs_raw]
        if not return_legs_raw:
            # Falls die Heuristik fehlschlägt: Datenquelle liefert evtl. nur den Outbound-Teil separat.
            return None

        outbound_legs = _extract_legs(outbound_legs_raw)
        return_legs = _extract_legs(return_legs_raw)

        price_total_raw = candidate.get("price")
        if price_total_raw is None:
            return None
        price_per_person = price_total_raw / config.ADULTS

        outbound_duration = sum(l.duration_minutes for l in outbound_legs) + sum(_layovers_minutes(layovers))
        return_duration = sum(l.duration_minutes for l in return_legs)

        offer = FlightOffer(
            price_per_person=round(price_per_person, 2),
            price_total=int(price_total_raw),
            passengers=config.ADULTS,
            currency=config.CURRENCY,
            outbound_date=outbound_date,
            return_date=return_date,
            outbound_legs=outbound_legs,
            return_legs=return_legs,
            outbound_duration_minutes=outbound_duration,
            return_duration_minutes=return_duration,
            outbound_stops=max(0, len(outbound_legs) - 1),
            return_stops=max(0, len(return_legs) - 1),
            outbound_layovers_minutes=_layovers_minutes(layovers),
            return_layovers_minutes=[],
            airline_primary=outbound_legs[0].airline if outbound_legs else "unbekannt",
            travel_class=outbound_legs[0].travel_class if outbound_legs else config.TRAVEL_CLASS_NAME,
            baggage=_extract_baggage(candidate, priced_data),
            booking_link=_extract_booking_link(priced_data),
            data_source="SerpApi/GoogleFlights",
            is_self_transfer=_detect_self_transfer(layovers),
        )
        return offer
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Konnte Angebot nicht normalisieren (API-Format evtl. geändert): %s", exc)
        return None


def config_max_slip():
    """Kleine Toleranz, um Mitternachts-Flüge korrekt dem Outbound-Tag zuzuordnen."""
    from datetime import timedelta
    return timedelta(days=2)
