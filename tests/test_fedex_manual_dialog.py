import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from modules.fedex_manual_pod import ManualPageSave
from ui.fedex_manual_dialog import (
    FedExManualDialog,
    ManualPodWorker,
    SegmentedAutoPodWorker,
)


class ManualDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_exposes_human_search_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            dialog = FedExManualDialog(["541964339019"], folder)
            self.assertEqual("开始", dialog.start_button.text())
            self.assertEqual("暂停", dialog.pause_button.text())
            self.assertEqual("恢复", dialog.resume_button.text())
            self.assertEqual("保存", dialog.print_button.text())
            self.assertTrue(dialog.automatic_switch.isChecked())
            self.assertTrue(dialog.segment_switch.isChecked())
            self.assertFalse(dialog.segment_switch.isHidden())
            self.assertTrue(dialog.print_button.isHidden())
            self.assertEqual("分段", dialog.segment_label.text())
            dialog.segment_switch.setChecked(False)
            self.assertEqual("连续", dialog.segment_label.text())
            dialog.segment_switch.setChecked(True)
            self.assertFalse(dialog.pin_switch.isChecked())
            self.assertTrue(dialog.windowFlags() & Qt.Window)
            dialog.automatic_switch.setChecked(False)
            self.assertTrue(dialog.segment_switch.isHidden())
            self.assertFalse(dialog.print_button.isHidden())
            dialog.close()

    def test_segmented_mode_is_separate_and_opt_in(self):
        with tempfile.TemporaryDirectory() as folder:
            dialog = FedExManualDialog(["541964339019"], folder)
            with mock.patch.object(SegmentedAutoPodWorker, "start") as start:
                dialog.start_segmented()
            self.assertIsInstance(dialog.worker, SegmentedAutoPodWorker)
            start.assert_called_once()
            dialog.worker = None
            dialog._active = False
            dialog.close()

    def test_segmented_worker_wait_can_be_stopped_immediately(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = SegmentedAutoPodWorker(
                os.path.join(folder, "queue.json"), folder
            )
            worker.stop_event.set()
            worker._interruptible_delay(300)
            self.assertTrue(worker.stop_event.is_set())

    def test_segmented_failure_uses_visible_warning(self):
        with tempfile.TemporaryDirectory() as folder:
            dialog = FedExManualDialog(["541964339019"], folder)
            with mock.patch("ui.fedex_manual_dialog.QMessageBox.warning") as warning:
                dialog._show_segmented_failure("直链失败")
            warning.assert_called_once_with(dialog, "FedEx 自动下载已暂停", "直链失败")
            dialog.close()

    def test_continuous_auto_mode_starts_without_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            dialog = FedExManualDialog(["541964339019"], folder)
            with mock.patch("ui.fedex_manual_dialog.ExperimentalAutoPodWorker") as worker:
                dialog.start_auto()
            self.assertIsInstance(dialog.worker, mock.Mock)
            self.assertFalse(dialog.segment_switch.isChecked())
            worker.assert_called_once()
            worker.return_value.start.assert_called_once()
            dialog._active = False
            dialog.worker = None
            dialog.close()

    def test_continuous_auto_processes_all_ready_queue_items(self):
        with tempfile.TemporaryDirectory() as folder:
            dialog = FedExManualDialog(["541964339019"], folder, auto_batch_limit=25)
            dialog.queue.add_numbers(["541964339020", "541964339021"])
            with mock.patch("ui.fedex_manual_dialog.ExperimentalAutoPodWorker") as worker:
                dialog.start_auto()
            self.assertEqual(3, worker.call_args.kwargs["batch_limit"])
            worker.return_value.start.assert_called_once()
            dialog._active = False
            dialog.worker = None
            dialog.close()

    def test_worker_does_not_advance_without_human_query(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = ManualPodWorker(
                ["541964339019"], folder, queue_path=os.path.join(folder, "queue.json")
            )
            session = mock.Mock()
            with mock.patch("ui.fedex_manual_dialog.time.sleep", side_effect=lambda _: worker.stop_event.set()):
                self.assertEqual("stop", worker._process(session, worker.queue.next_ready()))
            session.save_current.assert_not_called()

    def test_skip_current_is_honored_before_page_printing(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = ManualPodWorker(
                ["541964339019"], folder, queue_path=os.path.join(folder, "queue.json")
            )
            session = mock.Mock()
            worker.skip_event.set()
            self.assertEqual("skip", worker._process(session, worker.queue.next_ready()))
            session.save_current.assert_not_called()
            self.assertEqual("skipped", worker.queue.get("541964339019").state)

    def test_worker_prints_only_after_save_button_event(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = ManualPodWorker(
                ["541964339019"], folder, queue_path=os.path.join(folder, "queue.json")
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

    def test_manual_save_advances_and_copies_next_number_after_both_pages(self):
        with tempfile.TemporaryDirectory() as folder:
            queue_path = os.path.join(folder, "queue.json")
            worker = ManualPodWorker(["541964339019"], folder, queue_path=queue_path)
            worker.queue.add_numbers(["541964339020"])
            session = mock.Mock()
            session.save_current.side_effect = [
                ManualPageSave("main", os.path.join(folder, "main.pdf"), ("text", "url")),
                ManualPageSave("detail", os.path.join(folder, "detail.pdf")),
            ]
            worker.print_event.set()
            with mock.patch(
                "ui.fedex_manual_dialog.time.sleep",
                side_effect=lambda _seconds: worker.print_event.set(),
            ):
                outcome = worker._process(session, worker.queue.next_ready())
            self.assertEqual("done", outcome)
            self.assertEqual("completed", worker.queue.get("541964339019").state)
            self.assertEqual("541964339020", worker.queue.next_ready().number)

    def test_manual_dialog_has_no_next_ticket_button(self):
        with tempfile.TemporaryDirectory() as folder:
            dialog = FedExManualDialog(["541964339019"], folder)
            self.assertFalse(hasattr(dialog, "next_button"))
            dialog.close()

    def test_reconnect_event_opens_site_only_when_user_requests_it(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = ManualPodWorker(
                ["541964339019"], folder, queue_path=os.path.join(folder, "queue.json")
            )
            session = mock.Mock()
            worker.open_site_event.set()
            with mock.patch(
                "ui.fedex_manual_dialog.time.sleep", side_effect=lambda _: worker.stop_event.set()
            ):
                self.assertEqual("stop", worker._process(session, worker.queue.next_ready()))
            session.open_tracking_site.assert_called_once_with()
