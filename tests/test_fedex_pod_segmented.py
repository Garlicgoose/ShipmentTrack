import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules.fedex_pod_queue import FedExPodQueue
from modules.fedex_pod_segmented import (
    ITEM_INTERVAL_SECONDS,
    SEGMENT_PAUSE_SECONDS,
    SITE_COOLDOWN_SECONDS,
    plan_segments,
    run_segmented_auto,
)
from modules.fedex_web_pod import FedExWebPodResult


class SegmentedAutoPodTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.queue = FedExPodQueue(Path(self.temp_dir.name) / "queue.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    @staticmethod
    def _success(number):
        return FedExWebPodResult(number, True, f"{number}.pdf", f"{number}+.pdf")

    def test_segment_plan_matches_business_limits(self):
        self.assertEqual((), plan_segments(0))
        self.assertEqual((39,), plan_segments(39))
        self.assertEqual((40,), plan_segments(40))
        self.assertEqual((50,), plan_segments(50))
        self.assertEqual((25, 25, 1), plan_segments(51))
        self.assertEqual((25, 25, 25, 25), plan_segments(100))
        self.assertEqual((25, 25, 25, 25), plan_segments(150))

    def test_run_never_takes_more_than_one_hundred_jobs(self):
        numbers = [f"54196433{index:04d}" for index in range(105)]
        self.queue.add_numbers(numbers)
        session = mock.Mock()
        session.download.side_effect = self._success
        outcome = run_segmented_auto(
            self.queue,
            session,
            item_interval_seconds=0,
            segment_pause_seconds=0,
        )
        self.assertEqual(100, outcome.target)
        self.assertEqual(100, outcome.completed)
        self.assertEqual(100, session.download.call_count)
        self.assertEqual(5, self.queue.counts()["pending"])

    def test_more_than_fifty_uses_twenty_five_job_segments_and_pauses(self):
        numbers = [f"54196433{index:04d}" for index in range(51)]
        self.queue.add_numbers(numbers)
        session = mock.Mock()
        session.download.side_effect = self._success
        delays = []
        outcome = run_segmented_auto(self.queue, session, delay=delays.append)
        self.assertEqual(3, outcome.segments_completed)
        self.assertEqual(2, delays.count(SEGMENT_PAUSE_SECONDS))
        self.assertEqual(48, delays.count(ITEM_INTERVAL_SECONDS))

    def test_site_block_cools_down_then_probes_same_job(self):
        self.queue.add_numbers(["541964339019", "541964339020"])
        session = mock.Mock()
        session.download.side_effect = [
            FedExWebPodResult("541964339019", False, error="FedEx system-error"),
            self._success("541964339019"),
            self._success("541964339020"),
        ]
        delays = []
        outcome = run_segmented_auto(self.queue, session, delay=delays.append)
        self.assertEqual(2, outcome.completed)
        self.assertEqual(0, outcome.paused)
        self.assertEqual(3, outcome.requests)
        self.assertIn(SITE_COOLDOWN_SECONDS, delays)
        self.assertEqual("completed", self.queue.get("541964339019").state)

    def test_second_block_during_probe_stops_and_keeps_remaining_queue(self):
        self.queue.add_numbers(["541964339019", "541964339020"])
        session = mock.Mock()
        session.download.side_effect = [
            FedExWebPodResult("541964339019", False, error="请求过多"),
            FedExWebPodResult("541964339019", False, error="请求过多"),
        ]
        outcome = run_segmented_auto(self.queue, session, delay=lambda _seconds: None)
        self.assertTrue(outcome.site_blocked)
        self.assertEqual(1, outcome.paused)
        self.assertEqual("paused", self.queue.get("541964339019").state)
        self.assertEqual("pending", self.queue.get("541964339020").state)

    def test_single_job_failure_does_not_stop_other_jobs(self):
        self.queue.add_numbers(["541964339019", "541964339020"])
        session = mock.Mock()
        session.download.side_effect = [
            FedExWebPodResult("541964339019", False, error="详情按钮未出现"),
            self._success("541964339020"),
        ]
        outcome = run_segmented_auto(
            self.queue, session, item_interval_seconds=0
        )
        self.assertEqual(1, outcome.paused)
        self.assertEqual(1, outcome.completed)
        self.assertEqual("paused", self.queue.get("541964339019").state)
        self.assertEqual("completed", self.queue.get("541964339020").state)


if __name__ == "__main__":
    unittest.main()
