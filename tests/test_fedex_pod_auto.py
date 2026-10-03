import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modules.fedex_pod_auto import AUTO_BATCH_LIMIT, run_experimental_auto
from modules.fedex_pod_queue import FedExPodQueue
from modules.fedex_web_pod import FedExWebPodResult


class ExperimentalAutoPodTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.queue = FedExPodQueue(Path(self.temp_dir.name) / "queue.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_batch_is_hard_limited_to_ten(self):
        numbers = [f"54196433{index:04d}" for index in range(20)]
        self.queue.add_numbers(numbers)
        session = mock.Mock()
        session.download.side_effect = lambda number: FedExWebPodResult(
            number, True, f"{number}.pdf", f"{number}+.pdf"
        )
        result = run_experimental_auto(
            self.queue, session, batch_limit=99, interval_seconds=0
        )
        self.assertEqual(AUTO_BATCH_LIMIT, result.processed)
        self.assertEqual(AUTO_BATCH_LIMIT, result.completed)
        self.assertEqual(AUTO_BATCH_LIMIT, session.download.call_count)

    def test_site_block_pauses_current_and_opens_circuit_immediately(self):
        self.queue.add_numbers(["541964339019", "541964339020"])
        session = mock.Mock()
        session.download.return_value = FedExWebPodResult(
            "541964339019", False, error="FedEx system-error / 请求过多"
        )
        result = run_experimental_auto(self.queue, session, interval_seconds=0)
        self.assertTrue(result.circuit_open)
        self.assertEqual(1, result.processed)
        self.assertEqual("paused", self.queue.get("541964339019").state)
        self.assertEqual("pending", self.queue.get("541964339020").state)

    def test_two_ordinary_failures_open_circuit_without_retrying_same_job(self):
        self.queue.add_numbers(["541964339019", "541964339020", "541964339021"])
        session = mock.Mock()
        session.download.side_effect = [
            FedExWebPodResult("541964339019", False, error="详情按钮未出现"),
            FedExWebPodResult("541964339020", False, error="页面结构无法识别"),
        ]
        result = run_experimental_auto(self.queue, session, interval_seconds=0)
        self.assertTrue(result.circuit_open)
        self.assertEqual(2, result.processed)
        self.assertEqual(2, result.paused)
        self.assertEqual(2, session.download.call_count)

    def test_success_callback_receives_completed_result(self):
        self.queue.add_numbers(["541964339019"])
        pod_result = FedExWebPodResult(
            "541964339019", True, "main.pdf", "detail.pdf"
        )
        session = mock.Mock(download=mock.Mock(return_value=pod_result))
        callback = mock.Mock()
        result = run_experimental_auto(
            self.queue, session, interval_seconds=0, completed_callback=callback
        )
        self.assertEqual(1, result.completed)
        callback.assert_called_once_with(pod_result)
        self.assertEqual("completed", self.queue.get("541964339019").state)


if __name__ == "__main__":
    unittest.main()
