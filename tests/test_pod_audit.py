import random
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from openpyxl import load_workbook

from modules.pod_audit import (
    PodAuditItem,
    audit_pod_sample,
    choose_pod_samples,
    inspect_pod,
)


class FakePage:
    def __init__(self, text):
        self.text = text

    def extract_text(self):
        return self.text


class FakeReader:
    def __init__(self, text):
        self.pages = [FakePage(text)]


class PodAuditTests(unittest.TestCase):
    def test_pdf_inspection_requires_number_and_delivered_field(self):
        with mock.patch("modules.pod_audit.PdfReader", return_value=FakeReader(
            "Tracking number 123 456. Status: Delivered. Proof of Delivery"
        )):
            item = inspect_pod("123456.pdf", "123456", "FedEx")
        self.assertEqual("通过", item.result)
        self.assertTrue(item.tracking_found)
        self.assertTrue(item.delivered_found)

        with mock.patch("modules.pod_audit.PdfReader", return_value=FakeReader(
            "Tracking number 123456. Status: In transit"
        )):
            item = inspect_pod("123456.pdf", "123456", "FedEx")
        self.assertEqual("人工复核", item.result)
        self.assertFalse(item.delivered_found)

    def test_risk_shipments_are_always_selected_plus_random_minimum(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            results = []
            for index in range(10):
                pdf = root / f"{index}.pdf"
                pdf.write_bytes(b"%PDF-test")
                results.append({
                    "运单号": str(index),
                    "快递公司": "FedEx",
                    "状态": "Delivered",
                    "POD文件": str(pdf),
                    "备注": "人工复核：40条" if index == 0 else "",
                })
            selected = choose_pod_samples(results, rng=random.Random(7))
        self.assertIn((results[0], "风险必查"), selected)
        self.assertEqual(4, len(selected))

    def test_audit_writes_traceable_workbook(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            pdf = root / "123.pdf"
            pdf.write_bytes(b"%PDF-test")
            result = {
                "运单号": "123",
                "快递公司": "DHL",
                "状态": "Delivered",
                "POD文件": str(pdf),
                "备注": "人工复核",
            }

            def fake_inspector(pdf_file, tracking_number, carrier):
                return PodAuditItem(
                    tracking_number, carrier, str(pdf_file), "", True, True, True,
                    "通过", "",
                )

            output = root / "pod_audit.xlsx"
            items = audit_pod_sample([result], output, inspector=fake_inspector)
            workbook = load_workbook(output, data_only=True)
        self.assertEqual(1, len(items))
        self.assertEqual("风险必查", items[0].sample_reason)
        self.assertEqual("POD抽查", workbook.active.title)
        self.assertEqual("通过", workbook.active["H2"].value)


if __name__ == "__main__":
    unittest.main()
