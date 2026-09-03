import os
import tempfile
import unittest

from src import config, storage
from src.deal_engine import assess
from tests.helpers import make_offer


class TestStorage(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self._orig_db_path = config.DB_PATH
        config.DB_PATH = os.path.join(self._tmpdir.name, "test.db")
        storage.init_db()

    def tearDown(self):
        config.DB_PATH = self._orig_db_path
        self._tmpdir.cleanup()

    def test_save_and_read_observation(self):
        offer = make_offer(price_per_person=1300)
        assessment = assess(offer, historical_low_overall=None, previous_price_for_combo=None)
        storage.save_observation(offer, assessment)

        low = storage.get_historical_low()
        self.assertEqual(low, 1300)

    def test_historical_low_updates_correctly(self):
        offer1 = make_offer(price_per_person=1400)
        a1 = assess(offer1, None, None)
        storage.save_observation(offer1, a1)

        offer2 = make_offer(price_per_person=1250)
        a2 = assess(offer2, storage.get_historical_low(), None)
        storage.save_observation(offer2, a2)

        self.assertEqual(storage.get_historical_low(), 1250)

    def test_previous_price_for_combo(self):
        offer1 = make_offer(price_per_person=1400)
        storage.save_observation(offer1, assess(offer1, None, None))
        offer2 = make_offer(price_per_person=1350)
        storage.save_observation(offer2, assess(offer2, 1400, 1400))

        prev = storage.get_previous_price_for_combo(offer2.outbound_date, offer2.return_date)
        self.assertEqual(prev, 1400)

    def test_notified_keys_roundtrip(self):
        self.assertEqual(storage.get_notified_keys(), set())
        storage.mark_notified("some-key")
        self.assertIn("some-key", storage.get_notified_keys())

    def test_rotation_advances_and_wraps(self):
        total = len(config.ALL_COMBINATIONS)
        first = storage.get_next_combo_indices(4)
        self.assertEqual(first, [0, 1, 2, 3])
        storage.advance_rotation(4)
        second = storage.get_next_combo_indices(4)
        self.assertEqual(second, [4, 5, 6, 7])

        # Wrap-around testen: aktueller Stand ist 4, also (total - 4) weiterdrehen -> zurück auf 0
        storage.advance_rotation(total - 4)
        third = storage.get_next_combo_indices(4)
        self.assertEqual(third, [0, 1, 2, 3])

    def test_run_log_lifecycle(self):
        run_id = storage.start_run()
        storage.finish_run(run_id, "ok", combinations_checked=4, offers_found=2, api_calls_used=8)
        runs = storage.get_recent_runs(1)
        self.assertEqual(runs[0]["status"], "ok")
        self.assertEqual(runs[0]["api_calls_used"], 8)

    def test_consecutive_failed_runs_counts_correctly(self):
        for _ in range(3):
            rid = storage.start_run()
            storage.finish_run(rid, "failed", 4, 0, 8, "provider down")
        self.assertEqual(storage.get_consecutive_failed_runs(), 3)

        rid = storage.start_run()
        storage.finish_run(rid, "ok", 4, 1, 8)
        self.assertEqual(storage.get_consecutive_failed_runs(), 0)


if __name__ == "__main__":
    unittest.main()
