import unittest
from datetime import date

from src import filters
from tests.helpers import make_offer


class TestPriceCeiling(unittest.TestCase):
    def test_exact_1600_passes(self):
        offer = make_offer(price_per_person=1600.0)
        self.assertTrue(filters.passes_price_ceiling(offer))

    def test_1601_fails(self):
        offer = make_offer(price_per_person=1601.0)
        self.assertFalse(filters.passes_price_ceiling(offer))

    def test_total_3200_for_2_people(self):
        offer = make_offer(price_per_person=1600.0)
        self.assertEqual(offer.price_total, 3200)
        self.assertTrue(filters.passes_price_ceiling(offer))

    def test_total_over_3200_fails_even_if_pp_ok(self):
        offer = make_offer(price_per_person=1590.0)
        offer.price_total = 3300  # künstlich inkonsistent, um Gesamt-Check separat zu testen
        self.assertFalse(filters.passes_price_ceiling(offer))


class TestPremiumEconomyFilter(unittest.TestCase):
    def test_premium_economy_passes(self):
        offer = make_offer(travel_class="Premium Economy")
        self.assertTrue(filters.passes_travel_class(offer))

    def test_economy_fails(self):
        offer = make_offer(travel_class="Economy")
        self.assertFalse(filters.passes_travel_class(offer))


class TestDateWindow(unittest.TestCase):
    def test_inside_window_passes(self):
        offer = make_offer(outbound_date=date(2026, 12, 5), return_date=date(2027, 1, 10))
        self.assertTrue(filters.passes_date_window(offer))

    def test_outside_outbound_window_fails(self):
        offer = make_offer(outbound_date=date(2026, 11, 30), return_date=date(2027, 1, 10))
        self.assertFalse(filters.passes_date_window(offer))

    def test_outside_return_window_fails(self):
        offer = make_offer(outbound_date=date(2026, 12, 5), return_date=date(2027, 1, 16))
        self.assertFalse(filters.passes_date_window(offer))


class TestMaxDuration(unittest.TestCase):
    def test_17h_exact_passes(self):
        offer = make_offer(outbound_duration=17 * 60, return_duration=17 * 60)
        self.assertTrue(filters.passes_duration(offer))

    def test_over_17h_fails(self):
        offer = make_offer(outbound_duration=17 * 60 + 1)
        self.assertFalse(filters.passes_duration(offer))


class TestMaxStops(unittest.TestCase):
    def test_direct_passes(self):
        self.assertTrue(filters.passes_stops(make_offer(outbound_stops=0, return_stops=0)))

    def test_one_stop_passes(self):
        self.assertTrue(filters.passes_stops(make_offer(outbound_stops=1, return_stops=1)))

    def test_two_stops_fails(self):
        self.assertFalse(filters.passes_stops(make_offer(outbound_stops=2, return_stops=0)))


class TestSelfTransfer(unittest.TestCase):
    def test_no_self_transfer_passes(self):
        self.assertTrue(filters.passes_self_transfer(make_offer(is_self_transfer=False)))

    def test_self_transfer_fails(self):
        self.assertFalse(filters.passes_self_transfer(make_offer(is_self_transfer=True)))


class TestLayoverSanity(unittest.TestCase):
    def test_reasonable_layover_passes(self):
        offer = make_offer(outbound_stops=1, outbound_layovers=[90])
        self.assertTrue(filters.passes_layover_sanity(offer))

    def test_too_short_layover_fails(self):
        offer = make_offer(outbound_stops=1, outbound_layovers=[20])
        self.assertFalse(filters.passes_layover_sanity(offer))

    def test_too_long_layover_fails(self):
        offer = make_offer(outbound_stops=1, outbound_layovers=[1500])
        self.assertFalse(filters.passes_layover_sanity(offer))


class TestBaggageLogic(unittest.TestCase):
    def test_included_baggage_no_surcharge(self):
        offer = make_offer(price_per_person=1500, baggage_included=1, baggage_verified=True)
        self.assertEqual(offer.total_effective_price_per_person, 1500)

    def test_unverified_baggage_does_not_invent_cost(self):
        offer = make_offer(price_per_person=1500, baggage_included=0, baggage_verified=False)
        # Darf keine erfundenen Kosten addieren, Preis bleibt unverändert
        self.assertEqual(offer.total_effective_price_per_person, 1500)
        self.assertFalse(offer.baggage.verified)

    def test_extra_bag_cost_is_added(self):
        offer = make_offer(price_per_person=1500, baggage_included=0, baggage_verified=True)
        offer.baggage.extra_bag_cost_per_person = 80
        self.assertEqual(offer.total_effective_price_per_person, 1580)


class TestFullFilterIntegration(unittest.TestCase):
    def test_valid_offer_passes_everything(self):
        offer = make_offer()
        result = filters.evaluate(offer)
        self.assertTrue(result.passed, result.reasons_failed)

    def test_invalid_offer_lists_all_failed_reasons(self):
        offer = make_offer(price_per_person=2000, outbound_stops=3, travel_class="Economy")
        result = filters.evaluate(offer)
        self.assertFalse(result.passed)
        self.assertIn("Preisobergrenze", result.reasons_failed)
        self.assertIn("max. 1 Umstieg", result.reasons_failed)
        self.assertIn("Premium Economy", result.reasons_failed)


if __name__ == "__main__":
    unittest.main()
