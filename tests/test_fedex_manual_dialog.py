import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from modules.fedex_manual_pod import ManualPageSave
from ui.fedex_manual_dialog import FedExManualDialog, ManualPodWorker


class ManualDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_exposes_human_search_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            dialog = FedExManualDialog(["541964339019"], folder)
            self.assertIn("用户负责 TRACK", dialog.stage_label.text())
            self.assertEqual("打开浏览器并开始", dialog.start_button.text())
            self.assertEqual("保存当前页面 PDF", dialog.print_button.text())
            self.assertEqual("下一票", dialog.next_button.text())
            self.assertEqual("跳过当前", dialog.skip_button.text())
            self.assertTrue(dialog.windowFlags() & Qt.WindowStaysOnTopHint)
            self.assertTrue(dialog.windowFlags() & Qt.Window)
            dialog.close()

    def test_worker_does_not_advance_without_human_query(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = ManualPodWorker(
                ["541964339019"], folder, queue_path=os.path.join(folder, "queue.sqlite")
            )
            session = mock.Mock()
            with mock.patch("ui.fedex_manual_dialog.time.sleep", side_effect=lambda _: worker.stop_event.set()):
                self.assertEqual("stop", worker._process(session, worker.queue.next_ready()))
            session.save_current.assert_not_called()

    def test_skip_current_is_honored_before_page_printing(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = ManualPodWorker(
                ["541964339019"], folder, queue_path=os.path.join(folder, "queue.sqlite")
            )
            session = mock.Mock()
            worker.skip_event.set()
            self.assertEqual("skip", worker._process(session, worker.queue.next_ready()))
            session.save_current.assert_not_called()
            self.assertEqual("skipped", worker.queue.get("541964339019").state)

    def test_worker_prints_only_after_save_button_event(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = ManualPodWorker(
                ["541964339019"], folder, queue_path=os.path.join(folder, "queue.sqlite")
            )
            session = mock.Mock()
            session.save_current.return_value = ManualPageSave(
                "main", os.path.join(folder, "541964339019.pdf"), ("main", "url")
            )
            worker.print_event.set()
            with mock.patch(
                "ui.fedex_manual_dialog.time.sleep", side_effect=lambda _: worker.stop_event.set()
            ):
                self.assertEqual("stop", worker._process(session, worker.queue.next_ready()))
            session.save_current.assert_called_once_with("541964339019", "main", None)
            self.assertEqual("main_saved", worker.queue.get("541964339019").state)

    def test_next_does_not_navigate_or_advance_incomplete_task(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = ManualPodWorker(
                ["541964339019"], folder, queue_path=os.path.join(folder, "queue.sqlite")
            )
            session = mock.Mock()
            worker.next_event.set()
            with mock.patch(
                "ui.fedex_manual_dialog.time.sleep", side_effect=lambda _: worker.stop_event.set()
            ):
                self.assertEqual("stop", worker._process(session, worker.queue.next_ready()))
            session.page.goto.assert_not_called()
            self.assertEqual("pending", worker.queue.get("541964339019").state)
