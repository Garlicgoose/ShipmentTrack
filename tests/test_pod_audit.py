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

    def test_each_carrier_uses_its_own_zero_to_hundred_percent_rate(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            results = []
            for index in range(50):
                pdf = root / f"{index}.pdf"
                detail_pdf = root / f"{index}+.pdf"
                pdf.write_bytes(b"%PDF-test")
                detail_pdf.write_bytes(b"%PDF-test")
                carrier = ("FedEx", "DHL", "UPS", "EI", "DSV")[index // 10]
                results.append({
                    "运单号": str(index),
                    "快递公司": carrier,
                    "状态": "Delivered",
                    "POD文件": str(pdf),
                    "POD详情文件": str(detail_pdf) if carrier == "FedEx" else "",
                    "备注": "",
                })
            selected = choose_pod_samples(
                results,
                sample_rates={"FedEx": 10, "DHL": 20, "UPS": 30, "EI": 40, "DSV": 50},
                rng=random.Random(7),
            )
        self.assertEqual(16, len(selected))
        reasons = [item[1] for item in selected]
        self.assertEqual(2, reasons.count("FedEx 10%随机抽查"))
        self.assertEqual(2, reasons.count("DHL 20%随机抽查"))
        self.assertEqual(3, reasons.count("UPS 30%随机抽查"))
        self.assertEqual(4, reasons.count("EI 40%随机抽查"))
        self.assertEqual(5, reasons.count("DSV 50%随机抽查"))

    def test_zero_percent_disables_one_carrier_without_affecting_others(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            rows = []
            for carrier in ("FedEx", "DHL"):
                pdf = root / f"{carrier}.pdf"
                detail = root / f"{carrier}+.pdf"
                pdf.write_bytes(b"%PDF-test")
                detail.write_bytes(b"%PDF-test")
                rows.append({"运单号": carrier, "快递公司": carrier, "状态": "Delivered",
                             "POD文件": str(pdf), "POD详情文件": str(detail)})
            selected = choose_pod_samples(
                rows, sample_rates={"FedEx": 0, "DHL": 100}, rng=random.Random(1)
            )
        self.assertEqual(["DHL"], [item[0]["快递公司"] for item in selected])

    def test_all_zero_rates_remove_stale_audit_workbook(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "pod_audit.xlsx"
            output.write_bytes(b"stale")
            items = audit_pod_sample(
                [],
                output,
                sample_rates={carrier: 0 for carrier in ("FedEx", "DHL", "UPS", "EI", "DSV")},
            )
            self.assertEqual([], items)
            self.assertFalse(output.exists())

    def test_fedex_web_pod_no_longer_requires_signature_field(self):
        delivered = FakeReader("Tracking number 492670345899. Status: Delivered.")
        with mock.patch("modules.pod_audit.PdfReader", return_value=delivered):
            item = inspect_pod("492670345899.pdf", "492670345899", "FedEx")
        self.assertEqual("通过", item.result)

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
        self.assertEqual("DHL 5%随机抽查", items[0].sample_reason)
        self.assertEqual("POD抽查", workbook.active.title)
        self.assertEqual("Delivered", workbook.active["E2"].value)
        self.assertEqual("POD", workbook.active["C2"].value)
        self.assertEqual(0.05, workbook.active["D2"].value)
        self.assertEqual("Status: Delivered", workbook.active["I2"].value)
        self.assertEqual("通过", workbook.active["K2"].value)
        headers = [cell.value for cell in workbook.active[1]]
        self.assertNotIn("FedEx签收人字段", headers)

    def test_fedex_selected_shipment_audits_both_pdf_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            main = root / "12345678.pdf"
            detail = root / "12345678+.pdf"
            main.write_bytes(b"%PDF-main")
            detail.write_bytes(b"%PDF-detail")
            seen = []

            def fake_inspector(pdf_file, tracking_number, carrier):
                seen.append(str(pdf_file))
                return PodAuditItem(
                    str(tracking_number), str(carrier), str(pdf_file), "", "",
                    True, True, True, "Delivered", "通过", "",
                )

            items = audit_pod_sample(
                [{
                    "运单号": "12345678", "快递公司": "FedEx",
                    "状态": "Delivered", "POD文件": str(main),
                    "POD详情文件": str(detail),
                }],
                root / "audit.xlsx",
                inspector=fake_inspector,
                rng=random.Random(1),
            )
        self.assertEqual([str(main), str(detail)], seen)
        self.assertEqual(2, len(items))

    def test_missing_fedex_detail_path_is_a_failed_audit(self):
        item = inspect_pod("", "12345678", "FedEx")
        self.assertEqual("失败", item.result)
        self.assertIn("路径为空", item.details)


if __name__ == "__main__":
    unittest.main()
