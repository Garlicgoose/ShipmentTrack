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
    def __init__(self, text, images=()):
        self.text = text
        self.images = images

    def extract_text(self):
        return self.text

    def get(self, _key):
        return None


class FakeImage:
    def __init__(self, size):
        self.image = type("Image", (), {"size": size})()


class FakeReader:
    def __init__(self, text, images=()):
        self.pages = [FakePage(text, images)]


class PodAuditTests(unittest.TestCase):
    def test_pdf_inspection_requires_number_and_delivered_field(self):
        with mock.patch("modules.pod_audit.PdfReader", return_value=FakeReader(
            "Tracking number 123 456. Status: Delivered. Proof of Delivery"
        )):
            item = inspect_pod("123456.pdf", "123456", "DHL")
        self.assertEqual("通过", item.result)
        self.assertTrue(item.tracking_found)
        self.assertTrue(item.delivered_found)
        self.assertIn("Delivered", item.status_field)

        with mock.patch("modules.pod_audit.PdfReader", return_value=FakeReader(
            "Tracking number 123456. Status: In transit"
        )):
            item = inspect_pod("123456.pdf", "123456", "DHL")
        self.assertEqual("人工复核", item.result)
        self.assertFalse(item.delivered_found)

    def test_all_carrier_pods_are_sampled_at_five_percent(self):
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
        self.assertEqual(3, len(selected))
        self.assertTrue(all(item[1] == "全部POD随机抽查5%" for item in selected))

    def test_fedex_requires_signature_image_instead_of_delivered_text(self):
        signed = FakeReader(
            "Tracking number 492670345899. Status: Delivered. Signed for by:",
            [FakeImage((400, 95)), FakeImage((544, 160))],
        )
        with mock.patch("modules.pod_audit.PdfReader", return_value=signed):
            item = inspect_pod("492670345899.pdf", "492670345899", "FedEx")
        self.assertEqual("通过", item.result)
        self.assertTrue(item.signature_found)

        unsigned = FakeReader(
            "Tracking number 492670345899. Status: Delivered. Signed for by:",
            [FakeImage((544, 160))],
        )
        with mock.patch("modules.pod_audit.PdfReader", return_value=unsigned):
            item = inspect_pod("492670345899.pdf", "492670345899", "FedEx")
        self.assertEqual("人工复核", item.result)
        self.assertFalse(item.signature_found)
        self.assertIn("签名图像", item.details)

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
        self.assertEqual("全部POD随机抽查5%", items[0].sample_reason)
        self.assertEqual("POD抽查", workbook.active.title)
        self.assertEqual("Delivered", workbook.active["E2"].value)
        self.assertEqual("Status: Delivered", workbook.active["H2"].value)
        self.assertEqual("否", workbook.active["J2"].value)
        self.assertEqual("通过", workbook.active["K2"].value)


if __name__ == "__main__":
    unittest.main()
