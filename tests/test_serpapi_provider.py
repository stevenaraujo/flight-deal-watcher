import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from src import config
from src.providers import serpapi_provider
from src.providers.serpapi_provider import InvalidApiKeyError, ProviderError, RateLimitError, _normalize_offer


def _raw_leg(dep_airport, arr_airport, dep_time, arr_time, flight_number="LX8084", airline="SWISS", travel_class="Premium Economy", duration=600):
    return {
        "airline": airline,
        "flight_number": flight_number,
        "travel_class": travel_class,
        "duration": duration,
        "departure_airport": {"id": dep_airport, "time": dep_time},
        "arrival_airport": {"id": arr_airport, "time": arr_time},
    }


class TestNormalizeOffer(unittest.TestCase):
    def test_normalizes_direct_round_trip_correctly(self):
        candidate = {
            "flights": [
                _raw_leg("ZRH", "GRU", "2026-12-03 22:00", "2026-12-04 06:00"),
                _raw_leg("GRU", "GIG", "2027-01-10 08:00", "2027-01-10 09:15", flight_number="LX8085"),
            ],
            "layovers": [],
            "price": 2600,  # Gesamtpreis für 2 Personen
        }
        priced_data = {
            "booking_options": [
                {"together": {"booking_request": {"url": "https://example.com/book"}}}
            ],
            "baggage_prices": ["1st checked bag: free"],
        }
        offer = _normalize_offer(candidate, date(2026, 12, 3), date(2027, 1, 10), priced_data)
        self.assertIsNotNone(offer)
        self.assertEqual(offer.price_per_person, 1300.0)
        self.assertEqual(offer.price_total, 2600)
        self.assertEqual(offer.baggage.checked_bags_included, 1)
        self.assertTrue(offer.baggage.verified)
        self.assertEqual(offer.booking_link, "https://example.com/book")

    def test_missing_price_returns_none(self):
        candidate = {
            "flights": [_raw_leg("ZRH", "GIG", "2026-12-03 22:00", "2026-12-04 10:00")],
            "layovers": [],
        }
        offer = _normalize_offer(candidate, date(2026, 12, 3), date(2027, 1, 10), {})
        self.assertIsNone(offer)

    def test_unverified_baggage_when_no_info(self):
        candidate = {
            "flights": [
                _raw_leg("ZRH", "GRU", "2026-12-03 22:00", "2026-12-04 06:00"),
                _raw_leg("GRU", "GIG", "2027-01-10 08:00", "2027-01-10 09:15"),
            ],
            "layovers": [],
            "price": 2400,
        }
        offer = _normalize_offer(candidate, date(2026, 12, 3), date(2027, 1, 10), {})
        self.assertIsNotNone(offer)
        self.assertFalse(offer.baggage.verified)

    def test_malformed_flight_data_does_not_crash(self):
        candidate = {"flights": [{"broken": "data"}], "layovers": [], "price": 1000}
        offer = _normalize_offer(candidate, date(2026, 12, 3), date(2027, 1, 10), {})
        self.assertIsNone(offer)  # muss sauber None liefern, nicht crashen


class TestApiErrorHandling(unittest.TestCase):
    def setUp(self):
        self._orig_key = config.SERPAPI_API_KEY
        config.SERPAPI_API_KEY = "test-key"

    def tearDown(self):
        config.SERPAPI_API_KEY = self._orig_key

    def test_missing_api_key_raises(self):
        config.SERPAPI_API_KEY = None
        with self.assertRaises(InvalidApiKeyError):
            serpapi_provider._request({"engine": "google_flights"})

    @patch("src.providers.serpapi_provider.requests.get")
    def test_401_raises_invalid_key_error(self, mock_get):
        mock_resp = MagicMock(status_code=401, text="unauthorized")
        mock_get.return_value = mock_resp
        with self.assertRaises(InvalidApiKeyError):
            serpapi_provider._request({"engine": "google_flights"})

    @patch("src.providers.serpapi_provider.time.sleep", return_value=None)
    @patch("src.providers.serpapi_provider.requests.get")
    def test_429_retries_then_raises_rate_limit(self, mock_get, _mock_sleep):
        mock_resp = MagicMock(status_code=429, text="rate limited")
        mock_get.return_value = mock_resp
        with self.assertRaises(RateLimitError):
            serpapi_provider._request({"engine": "google_flights"})
        self.assertEqual(mock_get.call_count, serpapi_provider.MAX_RETRIES)

    @patch("src.providers.serpapi_provider.requests.get")
    def test_successful_response_returns_json(self, mock_get):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"best_flights": []}
        mock_get.return_value = mock_resp
        result = serpapi_provider._request({"engine": "google_flights"})
        self.assertEqual(result, {"best_flights": []})

    @patch("src.providers.serpapi_provider.requests.get")
    def test_no_departure_token_returns_empty_list(self, mock_get):
        mock_resp = MagicMock(status_code=200)
        mock_resp.json.return_value = {"best_flights": [{"price": 1000}]}  # kein departure_token
        mock_get.return_value = mock_resp
        offers = serpapi_provider.search_round_trip(date(2026, 12, 3), date(2027, 1, 10))
        self.assertEqual(offers, [])


if __name__ == "__main__":
    unittest.main()
