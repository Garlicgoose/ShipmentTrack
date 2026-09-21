import tempfile
import unittest
from pathlib import Path
from unittest import mock
from openpyxl import Workbook, load_workbook

from modules import fedex_manual_pod as manual


class ManualFedExPodTests(unittest.TestCase):
    def test_prepare_arms_input_after_user_click_without_submitting(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(manual, "RealBrowserController") as controller_type:
            page = mock.Mock(url="https://www.fedex.com/en-cn/tracking.html")
            controller_type.return_value.start.return_value = (mock.Mock(), page)
            session = manual.ManualFedExPodSession(
                mock.Mock(), "msedge.exe", "edge", temp_dir
            )
            self.assertEqual("541964339019", session.prepare("5419 64339019"))
            script, number = page.evaluate.call_args.args
            self.assertEqual("541964339019", number)
            self.assertIn("pointerdown", script)
            self.assertNotIn("requestSubmit", script)
            page.click.assert_not_called()
            page.goto.assert_called_once_with(
                manual.TRACKING_PAGE, wait_until="domcontentloaded", timeout=45_000
            )

    def test_detail_requires_current_number_and_changed_page(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(manual, "RealBrowserController"):
            session = manual.ManualFedExPodSession(mock.Mock(), "msedge.exe", "edge", temp_dir)
            session.page = mock.Mock(url="https://www.fedex.com/fedextrack/")
            before = ("541964339019\nDelivered", "https://www.fedex.com/fedextrack/")
            with mock.patch.object(manual, "_body_text", return_value="Travel History 541964339020" + "x" * 100):
                self.assertFalse(session.detail_ready("541964339019", before))
            with mock.patch.object(manual, "_body_text", return_value="Travel History 541964339019" + "x" * 100):
                self.assertTrue(session.detail_ready("541964339019", before))

    def test_blocked_page_never_prints(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
             mock.patch.object(manual, "RealBrowserController"), \
             mock.patch.object(manual, "_print_current_page") as printer:
            session = manual.ManualFedExPodSession(mock.Mock(), "msedge.exe", "edge", temp_dir)
            session.page = mock.Mock(url="https://www.fedex.com/en-cn/tracking.html")
            with mock.patch.object(manual, "_body_text", return_value="captcha 541964339019"):
                with self.assertRaisesRegex(RuntimeError, "验证码"):
                    session.save_main("541964339019")
            printer.assert_not_called()

    def test_manual_pod_paths_update_existing_tracking_excel(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "tracking_result.xlsx"
            book = Workbook()
            book.active.append(("运单号", "快递公司", "POD文件", "POD详情文件"))
            book.active.append(("541964339019", "FedEx", "", ""))
            book.save(path)
            self.assertTrue(manual.update_tracking_result_file(
                path, manual.ManualPodResult("541964339019", "main.pdf", "detail.pdf")
            ))
            output = load_workbook(path, read_only=True)
            self.assertEqual("main.pdf", output.active["C2"].value)
            self.assertEqual("detail.pdf", output.active["D2"].value)
            output.close()
