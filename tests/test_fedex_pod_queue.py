import tempfile
import unittest
import json
from pathlib import Path

from openpyxl import Workbook

from modules.fedex_pod_queue import FedExPodQueue


class FedExPodQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.queue = FedExPodQueue(self.root / "fedex_pod_queue.json")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_add_deduplicates_and_preserves_order(self):
        added = self.queue.add_numbers(
            ["5419 64339019", "541964339020", "541964339019", "bad"],
            source="tracking_result.xlsx",
        )
        self.assertEqual(["541964339019", "541964339020"], added)
        tasks = self.queue.tasks()
        self.assertEqual(["541964339019", "541964339020"], [task.number for task in tasks])
        self.assertTrue(all(task.source == "tracking_result.xlsx" for task in tasks))

    def test_import_excel_requires_named_tracking_column(self):
        path = self.root / "jobs.xlsx"
        book = Workbook()
        book.active.append(("备注", "运单号"))
        book.active.append(("a", "541964339019"))
        book.active.append(("b", "541964339019"))
        book.active.append(("c", "541964339020"))
        book.save(path)
        self.assertEqual(
            ["541964339019", "541964339020"], self.queue.import_excel(path)
        )

        invalid = self.root / "invalid.xlsx"
        book = Workbook()
        book.active.append(("Tracking Number",))
        book.save(invalid)
        with self.assertRaisesRegex(ValueError, "运单号"):
            self.queue.import_excel(invalid)

    def test_main_detail_state_survives_reopening_database(self):
        self.queue.add_numbers(["541964339019"])
        self.queue.mark_main_saved("541964339019", "main.pdf")
        reopened = FedExPodQueue(self.queue.path)
        task = reopened.next_ready()
        self.assertEqual("main_saved", task.state)
        self.assertEqual("detail", task.expected_page)
        reopened.mark_completed(task.number, "main.pdf", "detail.pdf")
        self.assertIsNone(reopened.next_ready())
        self.assertEqual("completed", reopened.get(task.number).state)

    def test_paused_tasks_wait_for_explicit_resume(self):
        self.queue.add_numbers(["541964339019", "541964339020"])
        self.queue.pause("541964339019", "FedEx 限流")
        self.assertEqual("541964339020", self.queue.next_ready().number)
        paused = self.queue.get("541964339019")
        self.assertEqual("paused", paused.state)
        self.assertEqual("FedEx 限流", paused.reason)
        self.queue.resume("541964339019")
        self.assertEqual("541964339019", self.queue.next_ready().number)

    def test_counts_include_every_queue_state(self):
        self.queue.add_numbers(["541964339019", "541964339020", "541964339021"])
        self.queue.mark_main_saved("541964339019", "main.pdf")
        self.queue.pause("541964339020", "等待人工")
        self.queue.skip("541964339021")
        self.assertEqual(
            {
                "total": 3,
                "pending": 0,
                "main_saved": 1,
                "completed": 0,
                "paused": 1,
                "skipped": 1,
            },
            self.queue.counts(),
        )

    def test_queue_is_plain_json_without_sqlite_runtime_dependency(self):
        self.queue.add_numbers(["541964339019"])
        document = json.loads(self.queue.path.read_text("utf-8"))
        self.assertEqual(1, document["version"])
        self.assertEqual("541964339019", document["tasks"][0]["number"])
        self.assertEqual([], list(self.queue.path.parent.glob(f".{self.queue.path.name}.*.tmp")))


if __name__ == "__main__":
    unittest.main()
