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

    def test_long_real_heading_does_not_turn_completed_into_unknown(self):
        body = (
            "Shipment: 4915209868 | Status: Completed "
            "MACAU to BANGKOK | Services Completed Notified Customers Broker "
            "Arrived at Final Port: 13-OCT-2026 ICT Details Events References "
            "Shipment Timeline"
        )
        self.assertGreater(
            len(body.split("Status:", 1)[1].split("Details", 1)[0]),
            100,
        )
        self.assertEqual("Completed", ei.extract_status(body))

    @mock.patch.object(ei.time, "sleep")
    def test_detail_wait_ignores_shell_until_current_status_renders(self, _sleep):
        page = mock.Mock()
        page.locator.return_value.inner_text.side_effect = [
            "Shipment: 4915209868 Details Events References",
            "Shipment: 4915209868 Status: Completed Details Events References",
        ]
        page.evaluate.return_value = []

        self.assertTrue(ei.wait_for_detail_page(page, "4915209868"))
        self.assertEqual(2, page.locator.return_value.inner_text.call_count)

    def test_query_reports_load_failure_instead_of_false_unknown(self):
        page = mock.Mock()
        page.locator.return_value.inner_text.return_value = (
            "Shipment: 4915209868 Details Events References"
        )
        with mock.patch.object(ei, "open_expeditors_detail_page", return_value=False), \
             mock.patch.object(ei, "close_expo_welcome_popup_once"), \
             mock.patch.object(ei, "remove_overlays"):
            result = ei.query_expeditors_one(page, "4915209868", save_pdf=False)

        self.assertEqual("Error", result["status"])
        self.assertIn("未显示当前状态", result["error"])


if __name__ == "__main__":
    unittest.main()
