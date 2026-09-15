import unittest
from unittest import mock

from modules.dhl_module import (
    DHL_STATUS_EXACT_LIST,
    extract_last_update_date,
    extract_status_from_text,
    extract_status_from_dom,
    is_dhl_strict_delivered,
    normalize_tracking_number,
)


class DhlStatusTests(unittest.TestCase):
    CLEARANCE_PAGE = """
Track & Trace
Tracking Code: 8124802604
Clearance Event
Last Update: Thursday, 3 September 2026 at 7:11 pm (UTC +03:00)
Shipment is on hold
Shipment Timeline
Thursday 3 September 2026 7:11 pm
Clearance Event
Tuesday 1 September 2026 3:01 pm
Shipment picked up
"""

    def test_clearance_page_is_not_delivered(self):
        status = extract_status_from_text(self.CLEARANCE_PAGE)
        self.assertEqual("Clearance Event", status)
        self.assertFalse(is_dhl_strict_delivered(status))

    def test_only_exact_delivered_is_accepted(self):
        self.assertTrue(is_dhl_strict_delivered("Delivered"))
        self.assertTrue(is_dhl_strict_delivered("delivered."))
        for status in (
            "Out for Delivery",
            "Delivery",
            "Delivered to service point",
            "Shipment is out with courier for delivery",
            "",
        ):
            self.assertFalse(is_dhl_strict_delivered(status), status)

    def test_body_text_never_confirms_delivered_from_history(self):
        self.assertEqual(
            "Unknown",
            extract_status_from_text("Tracking\nDelivered\nSigned by A. Chen"),
        )
        status = extract_status_from_text(
            "Shipment is out with courier for delivery\n"
            "Estimated delivery today\n"
            "Delivered to service point"
        )
        self.assertNotEqual("Delivered", status)

    def test_current_status_dom_ignores_history_and_uses_ranked_candidate(self):
        page = mock.Mock()
        page.evaluate.return_value = [
            {"text": "Shipment is out with courier for delivery", "score": 150, "top": 200},
            {"text": "Delivered", "score": 50, "top": 900},
        ]
        self.assertEqual(
            "Shipment is out with courier for delivery",
            extract_status_from_dom(page),
        )

    def test_custom_delivered_status_is_exact_and_dom_scoped(self):
        import modules.dhl_module as dhl
        original = dhl.CUSTOM_DELIVERED_STATUSES
        try:
            dhl.CUSTOM_DELIVERED_STATUSES = ("Handed to customs agent",)
            self.assertTrue(dhl.is_dhl_strict_delivered("Handed to customs agent"))
            self.assertFalse(dhl.is_dhl_strict_delivered("Handed to customs agent today"))
        finally:
            dhl.CUSTOM_DELIVERED_STATUSES = original

    def test_known_exception_states_are_supported(self):
        self.assertIn("Clearance Event", DHL_STATUS_EXACT_LIST)
        self.assertIn("Shipment is on hold", DHL_STATUS_EXACT_LIST)

    def test_delivery_date_and_tracking_number_normalization(self):
        self.assertEqual(
            ("3 September 2026", "2026/9/3"),
            extract_last_update_date(
                "Last Update: Thursday, 3 September 2026 at 7:11 pm (UTC +03:00)"
            ),
        )
        self.assertEqual("8124802604", normalize_tracking_number(" 8124 802604 "))
        self.assertEqual("", normalize_tracking_number(None))


if __name__ == "__main__":
    unittest.main()
