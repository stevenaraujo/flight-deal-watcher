"""Datenmodelle für einen normalisierten Flug-Deal, unabhängig vom Provider."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import List, Optional


@dataclass
class FlightLeg:
    """Ein einzelner Flugabschnitt (z.B. ZRH->GRU oder GRU->GIG)."""
    airline: str
    flight_number: str
    departure_airport: str
    arrival_airport: str
    departure_time: datetime
    arrival_time: datetime
    duration_minutes: int
    travel_class: str


@dataclass
class BaggageInfo:
    checked_bags_included: int  # Anzahl inkludierter Aufgabegepäckstücke
    verified: bool  # False = Datenquelle unsicher/unbekannt
    extra_bag_cost_per_person: Optional[float] = None  # falls bekannt


@dataclass
class FlightOffer:
    """Ein vollständig normalisiertes, bepreistes Round-Trip-Angebot."""
    # Preis
    price_per_person: float
    price_total: int  # Anzahl Personen wird separat mitgeführt
    passengers: int
    currency: str

    # Route / Zeiten
    outbound_date: date
    return_date: date
    outbound_legs: List[FlightLeg]
    return_legs: List[FlightLeg]

    # Abgeleitete Werte
    outbound_duration_minutes: int
    return_duration_minutes: int
    outbound_stops: int
    return_stops: int
    outbound_layovers_minutes: List[int]
    return_layovers_minutes: List[int]

    # Metadaten
    airline_primary: str
    travel_class: str
    baggage: BaggageInfo
    booking_link: Optional[str]
    data_source: str
    is_self_transfer: bool
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def total_effective_price_per_person(self) -> float:
        """Preis pro Person inkl. evtl. nicht inkludiertem Pflichtgepäck."""
        if self.baggage.checked_bags_included >= 1:
            return self.price_per_person
        if self.baggage.extra_bag_cost_per_person is not None:
            return self.price_per_person + self.baggage.extra_bag_cost_per_person
        # Gepäck nicht verifiziert -> Preis unverändert, aber Flag bleibt sichtbar
        return self.price_per_person

    @property
    def route_str(self) -> str:
        stops_out = [leg.arrival_airport for leg in self.outbound_legs[:-1]]
        via = f" -> {' -> '.join(stops_out)}" if stops_out else ""
        return f"{self.outbound_legs[0].departure_airport}{via} -> {self.outbound_legs[-1].arrival_airport}"

    def unique_key(self) -> str:
        """Eindeutiger Schlüssel für Duplikat-Erkennung (Flug + Datum + Preis-Bucket)."""
        flight_numbers = "-".join(l.flight_number for l in self.outbound_legs + self.return_legs)
        price_bucket = round(self.price_per_person / 5) * 5  # 5-CHF-Bucket glättet Mini-Schwankungen
        return f"{self.outbound_date}|{self.return_date}|{flight_numbers}|{price_bucket}"
