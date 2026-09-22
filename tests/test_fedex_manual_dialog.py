import os
import tempfile
import unittest
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

from ui.fedex_manual_dialog import FedExManualDialog, ManualPodWorker


class ManualDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_exposes_human_search_controls(self):
        with tempfile.TemporaryDirectory() as folder:
            dialog = FedExManualDialog(["541964339019"], folder)
            self.assertIn("自行打开 FedEx 网站", dialog.findChildren(type(dialog.current_label))[1].text())
            self.assertEqual("打开浏览器并开始", dialog.start_button.text())
            self.assertEqual("跳过当前", dialog.skip_button.text())
            self.assertTrue(dialog.windowFlags() & Qt.WindowStaysOnTopHint)
            self.assertTrue(dialog.windowFlags() & Qt.Window)
            dialog.close()

    def test_worker_does_not_advance_without_human_query(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = ManualPodWorker(["541964339019"], folder)
            session = mock.Mock()
            session.main_ready.return_value = False
            with mock.patch("ui.fedex_manual_dialog.time.sleep", side_effect=lambda _: worker.stop_event.set()):
                self.assertEqual("stop", worker._process(session, "541964339019"))
            session.save_main.assert_not_called()
            session.save_detail.assert_not_called()

    def test_skip_current_is_honored_before_page_printing(self):
        with tempfile.TemporaryDirectory() as folder:
            worker = ManualPodWorker(["541964339019"], folder)
            session = mock.Mock()
            worker.skip_event.set()
            self.assertEqual("skip", worker._process(session, "541964339019"))
            session.save_main.assert_not_called()
