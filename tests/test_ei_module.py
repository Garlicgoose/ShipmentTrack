import unittest
from unittest import mock

from modules import ei_module as ei


class ExpeditorsParsingTests(unittest.TestCase):
    def test_semantic_status_wins_over_route_and_history(self):
        page = mock.Mock()
        page.evaluate.return_value = [
            {"label": "Status", "value": "In Transit"},
        ]
        body = (
            "Status: In Transit Route HONG KONG to SHENZHEN "
            "Events Delivered 08-Oct-2026"
        )
        self.assertEqual("In Transit", ei.extract_labeled_status(page))
        self.assertEqual("In Transit", ei.extract_status(body, ei.extract_labeled_status(page)))
        self.assertFalse(ei.is_expeditors_delivered("In Transit", body))

    def test_delivered_is_a_current_delivered_status(self):
        self.assertEqual(
            "Delivered",
            ei.extract_status("Shipment Status: Delivered Route SHANGHAI to HONG KONG"),
        )
        self.assertTrue(ei.is_expeditors_delivered("Delivered", ""))

    def test_history_delivered_does_not_override_current_status(self):
        body = "Status: Booked Route HONG KONG to LAX Events Delivered yesterday"
        self.assertEqual("Booked", ei.extract_status(body))
        self.assertFalse(ei.is_expeditors_delivered(ei.extract_status(body), body))

    def test_unlabeled_timeline_status_is_not_treated_as_current(self):
        self.assertEqual(
            "Unknown",
            ei.extract_status("Shipment Timeline Delivered 08-Oct-2026"),
        )

    def test_semantic_extraction_failure_uses_labeled_text_fallback(self):
        page = mock.Mock()
        page.evaluate.side_effect = RuntimeError("navigation replaced document")
        self.assertEqual("", ei.extract_labeled_status(page))
        self.assertEqual("Completed", ei.extract_status("Current Status: Completed Details"))


if __name__ == "__main__":
    unittest.main()
