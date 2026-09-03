"""
Deal Engine.

Verantwortlich für:
- Klassifikation eines Preises in eine Deal-Stufe (config.DEAL_TIERS)
- Erkennung eines All-Time-Low gegenüber der Preishistorie
- Berechnung eines nachvollziehbaren Deal Score zur Sortierung
- Sortierung "bester tatsächlicher Preis pro Person zuerst"

Deal Score (dokumentierter Algorithmus):
  Der Score ist NIEDRIGER = BESSER (wie ein Golf-Score), damit er sich direkt
  mit dem Preis vergleichen lässt. Er addiert zum reinen Preis pro Person
  Aufschläge ("Strafpunkte" in CHF-Äquivalent) für schlechtere Reisequalität:

    score = preis_pro_person
            + 15 CHF je Umstieg (Hin+Rück zusammen)
            + 10 CHF je angefangene Stunde Reisezeit über dem direkten Minimum (8h)
            + 50 CHF, falls Gepäck nicht verifiziert (Risikoaufschlag)
            - 30 CHF, falls neues All-Time-Low (Bonus, um Rekorde nach oben zu sortieren)

  Damit bleibt der Score in derselben Grössenordnung wie ein Preis und ist
  für Menschen nachvollziehbar ("dieser Flug ist effektiv wie CHF X").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from . import config
from .models import FlightOffer

DIRECT_FLIGHT_BASELINE_MINUTES = 8 * 60  # ZRH-GIG Direktflug-Richtwert als Referenz


@dataclass
class DealAssessment:
    offer: FlightOffer
    tier_label: str
    is_all_time_low: bool
    previous_low: Optional[float]
    price_change_abs: Optional[float]  # ggü. letztem bekannten Preis für exakt diese Kombination
    price_change_pct: Optional[float]
    deal_score: float


def classify_price(price_per_person: float) -> str:
    for ceiling, label in config.DEAL_TIERS:
        if price_per_person <= ceiling:
            return label
    return config.NO_DEAL_LABEL


def compute_deal_score(offer: FlightOffer, is_all_time_low: bool) -> float:
    price = offer.total_effective_price_per_person
    stops_penalty = (offer.outbound_stops + offer.return_stops) * 15
    total_duration = offer.outbound_duration_minutes + offer.return_duration_minutes
    baseline = DIRECT_FLIGHT_BASELINE_MINUTES * 2
    extra_hours = max(0, (total_duration - baseline) // 60 + (1 if (total_duration - baseline) % 60 else 0))
    duration_penalty = extra_hours * 10
    baggage_penalty = 0 if offer.baggage.verified else 50
    atl_bonus = -30 if is_all_time_low else 0
    return round(price + stops_penalty + duration_penalty + baggage_penalty + atl_bonus, 2)


def assess(
    offer: FlightOffer,
    historical_low_overall: Optional[float],
    previous_price_for_combo: Optional[float],
) -> DealAssessment:
    price = offer.total_effective_price_per_person
    is_atl = historical_low_overall is None or price < historical_low_overall

    change_abs = None
    change_pct = None
    if previous_price_for_combo is not None:
        change_abs = round(price - previous_price_for_combo, 2)
        if previous_price_for_combo:
            change_pct = round((change_abs / previous_price_for_combo) * 100, 1)

    tier = classify_price(price)
    score = compute_deal_score(offer, is_atl)

    return DealAssessment(
        offer=offer,
        tier_label=tier,
        is_all_time_low=is_atl,
        previous_low=historical_low_overall,
        price_change_abs=change_abs,
        price_change_pct=change_pct,
        deal_score=score,
    )


def rank_offers(assessments: List[DealAssessment]) -> List[DealAssessment]:
    """Sortiert nach bestem tatsächlichem Preis pro Person (Haupt-Kriterium),
    Deal Score als Tie-Breaker für Angebote mit sehr ähnlichem Preis."""
    return sorted(
        assessments,
        key=lambda a: (a.offer.total_effective_price_per_person, a.deal_score),
    )


def should_notify(assessment: DealAssessment, already_notified_keys: set) -> bool:
    """Entscheidet, ob für dieses Angebot eine neue Benachrichtigung nötig ist
    (siehe storage.py für die Duplikat-Persistenz selbst)."""
    key = assessment.offer.unique_key()
    if key in already_notified_keys:
        return False
    if assessment.is_all_time_low:
        return True
    if assessment.tier_label == config.NO_DEAL_LABEL:
        return False
    if assessment.price_change_pct is not None and assessment.price_change_pct <= -5:
        return True
    # neuer, bisher unbekannter Deal innerhalb der Preisstufen
    return True
