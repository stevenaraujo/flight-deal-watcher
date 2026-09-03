import unittest

from src import config, deal_engine
from src.deal_engine import assess, classify_price, should_notify
from tests.helpers import make_offer


class TestDealClassification(unittest.TestCase):
    def test_extreme_deal(self):
        self.assertEqual(classify_price(999), "EXTREMER DEAL")
        self.assertEqual(classify_price(1000), "EXTREMER DEAL")

    def test_boundary_1000_to_1200(self):
        self.assertEqual(classify_price(1001), "SEHR STARKER DEAL")
        self.assertEqual(classify_price(1200), "SEHR STARKER DEAL")

    def test_boundary_1200_to_1400(self):
        self.assertEqual(classify_price(1201), "GUTER DEAL")
        self.assertEqual(classify_price(1400), "GUTER DEAL")

    def test_boundary_1400_to_1500(self):
        self.assertEqual(classify_price(1401), "INTERESSANT")
        self.assertEqual(classify_price(1500), "INTERESSANT")

    def test_boundary_1500_to_1600(self):
        self.assertEqual(classify_price(1501), "INNERHALB DER OBERGRENZE")
        self.assertEqual(classify_price(1600), "INNERHALB DER OBERGRENZE")

    def test_above_1600_no_deal(self):
        self.assertEqual(classify_price(1601), config.NO_DEAL_LABEL)


class TestAllTimeLow(unittest.TestCase):
    def test_first_price_ever_is_all_time_low(self):
        offer = make_offer(price_per_person=1400)
        result = assess(offer, historical_low_overall=None, previous_price_for_combo=None)
        self.assertTrue(result.is_all_time_low)

    def test_lower_than_historical_low_is_new_atl(self):
        offer = make_offer(price_per_person=1200)
        result = assess(offer, historical_low_overall=1300, previous_price_for_combo=1350)
        self.assertTrue(result.is_all_time_low)

    def test_equal_to_historical_low_is_not_new_atl(self):
        offer = make_offer(price_per_person=1300)
        result = assess(offer, historical_low_overall=1300, previous_price_for_combo=1300)
        self.assertFalse(result.is_all_time_low)

    def test_higher_than_historical_low_is_not_atl(self):
        offer = make_offer(price_per_person=1350)
        result = assess(offer, historical_low_overall=1300, previous_price_for_combo=1300)
        self.assertFalse(result.is_all_time_low)


class TestPriceChange(unittest.TestCase):
    def test_price_drop_computed_correctly(self):
        offer = make_offer(price_per_person=1289)
        result = assess(offer, historical_low_overall=1289, previous_price_for_combo=1395)
        self.assertEqual(result.price_change_abs, -106)
        self.assertAlmostEqual(result.price_change_pct, -7.6, places=1)


class TestDealScore(unittest.TestCase):
    def test_direct_flight_scores_lower_than_one_stop_at_same_price(self):
        direct = make_offer(price_per_person=1300, outbound_stops=0, return_stops=0)
        one_stop = make_offer(price_per_person=1300, outbound_stops=1, return_stops=1)
        score_direct = deal_engine.compute_deal_score(direct, is_all_time_low=False)
        score_stop = deal_engine.compute_deal_score(one_stop, is_all_time_low=False)
        self.assertLess(score_direct, score_stop)

    def test_unverified_baggage_increases_score(self):
        verified = make_offer(price_per_person=1300, baggage_verified=True)
        unverified = make_offer(price_per_person=1300, baggage_verified=False)
        score_verified = deal_engine.compute_deal_score(verified, is_all_time_low=False)
        score_unverified = deal_engine.compute_deal_score(unverified, is_all_time_low=False)
        self.assertLess(score_verified, score_unverified)


class TestDuplicateDetection(unittest.TestCase):
    def test_same_offer_not_notified_twice(self):
        offer = make_offer(price_per_person=1250)
        assessment = assess(offer, historical_low_overall=1250, previous_price_for_combo=None)
        key = assessment.offer.unique_key()
        already_notified = set()

        self.assertTrue(should_notify(assessment, already_notified))
        already_notified.add(key)
        self.assertFalse(should_notify(assessment, already_notified))

    def test_no_deal_tier_is_not_notified(self):
        offer = make_offer(price_per_person=1700)  # über Obergrenze -> hätte Filter eigentlich schon gestoppt
        assessment = assess(offer, historical_low_overall=1200, previous_price_for_combo=1700)
        self.assertFalse(should_notify(assessment, set()))

    def test_significant_price_drop_triggers_new_notification_even_if_seen_before_at_different_price(self):
        offer_v1 = make_offer(price_per_person=1400)
        assessment_v1 = assess(offer_v1, historical_low_overall=1400, previous_price_for_combo=None)
        key_v1 = assessment_v1.offer.unique_key()

        offer_v2 = make_offer(price_per_person=1250)  # deutlich günstiger -> anderer Preis-Bucket -> anderer Key
        assessment_v2 = assess(offer_v2, historical_low_overall=1250, previous_price_for_combo=1400)
        key_v2 = assessment_v2.offer.unique_key()

        self.assertNotEqual(key_v1, key_v2)
        self.assertTrue(should_notify(assessment_v2, {key_v1}))


if __name__ == "__main__":
    unittest.main()
