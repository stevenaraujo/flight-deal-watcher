"""Formatiert den Inhalt einer Deal-Benachrichtigung (für Telegram & E-Mail gemeinsam genutzt)."""
from __future__ import annotations

from ..deal_engine import DealAssessment


def format_deal_message(assessment: DealAssessment, historical_low: float | None) -> str:
    o = assessment.offer
    lines = []
    lines.append("✈️ FLUG-DEAL ZÜRICH → RIO")
    lines.append("")
    header = assessment.tier_label
    if assessment.is_all_time_low:
        header += "  🏆 NEUES ALL-TIME-LOW"
    lines.append(f"Deal-Kategorie: {header}")
    lines.append("")
    lines.append(f"Preis pro Person: CHF {o.total_effective_price_per_person:,.0f}")
    lines.append(f"Gesamtpreis für 2: CHF {o.price_total:,.0f}")

    if assessment.price_change_abs is not None:
        sign = "" if assessment.price_change_abs <= 0 else "+"
        lines.append(
            f"Preisänderung: {sign}CHF {assessment.price_change_abs:,.0f} "
            f"({sign}{assessment.price_change_pct:.1f} %)"
        )

    lines.append("")
    lines.append(f"Airline: {o.airline_primary}")
    if o.outbound_legs:
        lines.append(f"Hinflug: {o.outbound_date} ab {o.outbound_legs[0].departure_time.strftime('%H:%M')}")
    if o.return_legs:
        lines.append(f"Rückflug: {o.return_date} ab {o.return_legs[0].departure_time.strftime('%H:%M')}")
    lines.append(f"Route: {o.route_str}")

    if o.outbound_stops:
        via = o.outbound_legs[0].arrival_airport if o.outbound_legs else "?"
        dur = o.outbound_layovers_minutes[0] if o.outbound_layovers_minutes else 0
        lines.append(f"Umstieg: {via} ({dur // 60}h {dur % 60}min)")
    else:
        lines.append("Umstieg: Direktflug")

    total_h = (o.outbound_duration_minutes) // 60
    total_m = (o.outbound_duration_minutes) % 60
    lines.append(f"Gesamtreisezeit (Hinflug): {total_h}h {total_m:02d}min")

    lines.append(f"Premium Economy: {'bestätigt' if 'premium' in o.travel_class.lower() else 'nicht eindeutig bestätigt'}")

    if o.baggage.verified and o.baggage.checked_bags_included >= 1:
        baggage_txt = "1 Aufgabegepäck p. P. inklusive"
    elif o.baggage.verified:
        baggage_txt = "Zusatzkosten für Aufgabegepäck"
    else:
        baggage_txt = "nicht verifiziert"
    lines.append(f"Gepäck: {baggage_txt}")

    lines.append(f"Datenquelle: {o.data_source}")
    if o.booking_link:
        lines.append(f"Buchungs-/Suchlink: {o.booking_link}")
    lines.append(f"Zeitpunkt der Preisprüfung: {o.checked_at.strftime('%Y-%m-%d %H:%M UTC')}")

    lines.append("")
    if historical_low is not None:
        lines.append(f"Bisher günstigster Preis: CHF {historical_low:,.0f} p. P.")

    return "\n".join(lines)
