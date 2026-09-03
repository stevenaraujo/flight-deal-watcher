from datetime import date, datetime, timedelta

from src.models import BaggageInfo, FlightLeg, FlightOffer


def make_leg(dep="ZRH", arr="GRU", dep_time=None, dur=600, flight_number="LX8084", airline="SWISS", travel_class="Premium Economy"):
    dep_time = dep_time or datetime(2026, 12, 3, 10, 0)
    return FlightLeg(
        airline=airline,
        flight_number=flight_number,
        departure_airport=dep,
        arrival_airport=arr,
        departure_time=dep_time,
        arrival_time=dep_time + timedelta(minutes=dur),
        duration_minutes=dur,
        travel_class=travel_class,
    )


def make_offer(
    price_per_person=1300.0,
    outbound_date=date(2026, 12, 3),
    return_date=date(2027, 1, 10),
    outbound_duration=600,
    return_duration=600,
    outbound_stops=0,
    return_stops=0,
    baggage_included=1,
    baggage_verified=True,
    is_self_transfer=False,
    travel_class="Premium Economy",
    outbound_layovers=None,
    booking_link="https://example.com/book",
):
    return FlightOffer(
        price_per_person=price_per_person,
        price_total=int(price_per_person * 2),
        passengers=2,
        currency="CHF",
        outbound_date=outbound_date,
        return_date=return_date,
        outbound_legs=[make_leg(travel_class=travel_class)],
        return_legs=[make_leg(dep="GRU", arr="ZRH", travel_class=travel_class)],
        outbound_duration_minutes=outbound_duration,
        return_duration_minutes=return_duration,
        outbound_stops=outbound_stops,
        return_stops=return_stops,
        outbound_layovers_minutes=outbound_layovers or [],
        return_layovers_minutes=[],
        airline_primary="SWISS",
        travel_class=travel_class,
        baggage=BaggageInfo(checked_bags_included=baggage_included, verified=baggage_verified),
        booking_link=booking_link,
        data_source="SerpApi/GoogleFlights",
        is_self_transfer=is_self_transfer,
        checked_at=datetime(2026, 9, 3, 12, 0),
    )
