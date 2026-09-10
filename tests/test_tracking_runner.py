import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openpyxl import Workbook, load_workbook

from modules.tracking_runner import run_tracking
from modules.tracking_utils import prepare_tracking_input_rows


class TrackingRunnerTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
