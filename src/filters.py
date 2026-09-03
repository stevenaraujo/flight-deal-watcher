"""
Harte Filter-/Ausschlusskriterien. Alles hier ist eine reine Ja/Nein-Entscheidung
(Mindestanforderung erfüllt oder nicht) - die eigentliche Bewertung/Sortierung
"wie gut ist der Deal" passiert in deal_engine.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

from . import config
from .models import FlightOffer


@dataclass
class FilterResult:
    passed: bool
    reasons_failed: List[str]


def passes_price_ceiling(offer: FlightOffer) -> bool:
    """CHF 1'600 pro Person / CHF 3'200 Gesamt für 2 Personen - absolute Obergrenze."""
    return (
        offer.total_effective_price_per_person <= config.MAX_PRICE_PER_PERSON
        and offer.price_total <= config.MAX_PRICE_TOTAL
    )


def passes_duration(offer: FlightOffer) -> bool:
    return (
        offer.outbound_duration_minutes <= config.MAX_DURATION_MINUTES
        and offer.return_duration_minutes <= config.MAX_DURATION_MINUTES
    )


def passes_stops(offer: FlightOffer) -> bool:
    return offer.outbound_stops <= config.MAX_STOPS and offer.return_stops <= config.MAX_STOPS


def passes_self_transfer(offer: FlightOffer) -> bool:
    return not offer.is_self_transfer


def passes_layover_sanity(offer: FlightOffer) -> bool:
    for minutes in offer.outbound_layovers_minutes + offer.return_layovers_minutes:
        if minutes < config.MIN_LAYOVER_MINUTES or minutes > config.MAX_LAYOVER_MINUTES:
            return False
    return True


def passes_date_window(offer: FlightOffer) -> bool:
    out_ok = config.OUTBOUND_WINDOW[0] <= offer.outbound_date <= config.OUTBOUND_WINDOW[1]
    ret_ok = config.RETURN_WINDOW[0] <= offer.return_date <= config.RETURN_WINDOW[1]
    return out_ok and ret_ok


def passes_travel_class(offer: FlightOffer) -> bool:
    return config.TRAVEL_CLASS_NAME.lower() in offer.travel_class.lower()


ALL_CHECKS = [
    ("Preisobergrenze", passes_price_ceiling),
    ("Reisezeit <= 17h", passes_duration),
    ("max. 1 Umstieg", passes_stops),
    ("kein Self-Transfer", passes_self_transfer),
    ("Umsteigezeit plausibel", passes_layover_sanity),
    ("Datum im Suchfenster", passes_date_window),
    ("Premium Economy", passes_travel_class),
]


def evaluate(offer: FlightOffer) -> FilterResult:
    failed = [name for name, check in ALL_CHECKS if not check(offer)]
    return FilterResult(passed=len(failed) == 0, reasons_failed=failed)


def filter_offers(offers: List[FlightOffer]) -> List[FlightOffer]:
    """Gibt nur Angebote zurück, die alle Mindestanforderungen erfüllen."""
    return [o for o in offers if evaluate(o).passed]
