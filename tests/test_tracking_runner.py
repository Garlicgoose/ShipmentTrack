import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from openpyxl import Workbook, load_workbook

from modules.tracking_runner import _aggregate_audit_results, run_tracking
from modules.tracking_utils import prepare_tracking_input_rows


class TrackingRunnerTests(unittest.TestCase):
    def test_fedex_two_page_audit_uses_worst_result(self):
        items = [
            SimpleNamespace(tracking_number="123", result="通过"),
            SimpleNamespace(tracking_number="123", result="失败"),
        ]
        self.assertEqual({"123": "失败"}, _aggregate_audit_results(items))

    def test_openpyxl_input_reader_normalizes_and_sorts(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "input.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(("快递公司", "运单号"))
            sheet.append(("UPS", " 1Z 123 "))
            sheet.append(("fedex", 123456789012))
            workbook.save(path)
            rows = prepare_tracking_input_rows(path)
        self.assertEqual(["FedEx", "UPS"], [row["快递公司"] for row in rows])
        self.assertEqual("123456789012", rows[0]["运单号"])
        self.assertEqual("1Z123", rows[1]["运单号"])

    def test_result_callback_receives_each_row_and_status_only_is_forwarded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_file = root / "input.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(("快递公司", "运单号"))
            sheet.append(("FedEx", "123456789012"))
            workbook.save(input_file)

            emitted = []
            progress = []
            fake_result = {
                "status": "Delivered",
                "is_delivered": "Y",
                "arrival_time": "2026-09-10T12:30:00+08:00",
                "error": "",
                "flag": "",
            }
            with mock.patch(
                "modules.tracking_runner.fedex_module.query_fedex_one",
                return_value=fake_result,
            ) as query, mock.patch(
                "modules.tracking_runner.fedex_module.close_shared_session"
            ) as close:
                output = run_tracking(
                    input_file=input_file,
                    output_dir=root / "output",
                    fedex_api_key="key",
                    fedex_api_secret="secret",
                    save_pdf=False,
                    progress=progress.append,
                    result=emitted.append,
                )

            self.assertEqual(1, len(emitted))
            self.assertEqual("Delivered", emitted[0]["状态"])
            self.assertEqual("2026/9/10", emitted[0]["抵达时间"])
            self.assertEqual([100], progress)
            self.assertFalse(query.call_args.kwargs["save_pdf"])
            close.assert_called_once()

            result_book = load_workbook(output, data_only=True)
            self.assertEqual("123456789012", str(result_book.active["A2"].value))

    def test_delivered_fedex_uses_real_edge_for_two_web_pdfs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            input_file = root / "input.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.append(("快递公司", "运单号"))
            sheet.append(("FedEx", "519470439011"))
            workbook.save(input_file)
            emitted = []
            edge_session = mock.Mock()
            edge_session.download.return_value = SimpleNamespace(
                ok=True,
                main_pdf=str(root / "519470439011.pdf"),
                detail_pdf=str(root / "519470439011+.pdf"),
                error="",
            )
            playwright_manager = mock.Mock()
            playwright_manager.start.return_value = mock.Mock()
            with mock.patch(
                "modules.tracking_runner.fedex_module.query_fedex_one",
                return_value={
                    "status": "Delivered", "is_delivered": "Y",
                    "arrival_time": "2026-09-09", "error": "", "flag": "",
                },
            ) as query, mock.patch(
                "modules.tracking_runner.FedExEdgePodSession",
                return_value=edge_session,
            ) as edge, mock.patch(
                "playwright.sync_api.sync_playwright",
                return_value=playwright_manager,
            ), mock.patch(
                "modules.tracking_runner.audit_pod_sample", return_value=[]
            ):
                output = run_tracking(
                    input_file=input_file,
                    output_dir=root / "output",
                    fedex_api_key="key",
                    fedex_api_secret="secret",
                    chrome_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                    save_pdf=True,
                    result=emitted.append,
                )

            self.assertFalse(query.call_args.kwargs["save_pdf"])
            edge.assert_called_once()
            edge_session.download.assert_called_once_with("519470439011")
            edge_session.close.assert_called_once()
            self.assertTrue(emitted[0]["POD文件"].endswith("519470439011.pdf"))
            self.assertTrue(emitted[0]["POD详情文件"].endswith("519470439011+.pdf"))
            result_book = load_workbook(output, data_only=True)
            headers = [cell.value for cell in result_book.active[1]]
            self.assertIn("POD详情文件", headers)


if __name__ == "__main__":
    unittest.main()
