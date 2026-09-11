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
        self.assertIn("Delivered", item.status_field)

        with mock.patch("modules.pod_audit.PdfReader", return_value=FakeReader(
            "Tracking number 123456. Status: In transit"
        )):
            item = inspect_pod("123456.pdf", "123456", "FedEx")
        self.assertEqual("人工复核", item.result)
        self.assertFalse(item.delivered_found)

    def test_only_non_fedex_pods_are_sampled_at_five_percent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            results = []
            for index in range(50):
                pdf = root / f"{index}.pdf"
                pdf.write_bytes(b"%PDF-test")
                results.append({
                    "运单号": str(index),
                    "快递公司": "FedEx" if index < 10 else (
                        "DHL" if index % 2 else "DSV"
                    ),
                    "状态": "Delivered",
                    "POD文件": str(pdf),
                    "备注": "",
                })
            selected = choose_pod_samples(results, rng=random.Random(7))
        self.assertEqual(2, len(selected))
        self.assertTrue(all(item[0]["快递公司"] != "FedEx" for item in selected))
        self.assertTrue(all(item[1] == "非FedEx随机抽查5%" for item in selected))

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
                    tracking_number=tracking_number,
                    carrier=carrier,
                    pdf_file=str(pdf_file),
                    sample_reason="",
                    tracking_status="",
                    valid_pdf=True,
                    tracking_found=True,
                    delivered_found=True,
                    status_field="Status: Delivered",
                    result="通过",
                    details="",
                )

            output = root / "pod_audit.xlsx"
            items = audit_pod_sample([result], output, inspector=fake_inspector)
            workbook = load_workbook(output, data_only=True)
        self.assertEqual(1, len(items))
        self.assertEqual("非FedEx随机抽查5%", items[0].sample_reason)
        self.assertEqual("POD抽查", workbook.active.title)
        self.assertEqual("Delivered", workbook.active["E2"].value)
        self.assertEqual("Status: Delivered", workbook.active["H2"].value)
        self.assertEqual("通过", workbook.active["J2"].value)


if __name__ == "__main__":
    unittest.main()
