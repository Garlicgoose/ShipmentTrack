import unittest
from unittest import mock

from modules import ei_module as ei


class ExpeditorsParsingTests(unittest.TestCase):
    def test_wait_matches_s_tracking_number_with_display_separators(self):
        page = mock.Mock()
        page.locator.return_value.inner_text.return_value = (
            "Shipment S123-456 Status: In Transit"
        )
        page.evaluate.return_value = []
        self.assertTrue(ei.wait_for_detail_page(page, "S123456"))

    def test_detail_wait_accepts_correlated_api_result_without_page_status(self):
        page = mock.Mock()
        ready = mock.Mock(return_value=True)
        self.assertTrue(ei.wait_for_detail_page(page, "S123456", result_ready=ready))
        ready.assert_called_once_with()
        page.locator.assert_not_called()

    def test_graphql_result_requires_exact_reference_and_returns_status(self):
        request = {
            "operationName": "guestSearchShipmentsByReferenceNumber",
            "variables": {"referenceNumber": "S915237776"},
        }
        response = {
            "data": {
                "guestShipmentSearch": {
                    "status": {
                        "description": "Services Completed: Notified Customers Broker",
                        "lastStatusChangeEvent": {
                            "description": "Shipment Turned Over",
                            "formattedDate": "12-Oct-2026",
                        },
                    }
                }
            }
        }

        result = ei.extract_graphql_tracking_result(request, response, "S915237776")

        self.assertEqual("Services Completed", result["status"])
        self.assertEqual("Shipment Turned Over", result["last_event"])
        self.assertEqual("2026/10/12", result["status_date"])
        self.assertIsNone(
            ei.extract_graphql_tracking_result(
                {**request, "variables": {"referenceNumber": "prefix-S915237776-suffix"}},
                response,
                "S915237776",
            )
        )
        self.assertIsNone(
            ei.extract_graphql_tracking_result(
                {**request, "operationName": "retrieveShipmentByReferenceNumberForGuest"},
                response,
                "S915237776",
            )
        )

    def test_graphql_null_search_is_reported_as_no_result(self):
        result = ei.extract_graphql_tracking_result(
            {
                "operationName": "guestSearchShipmentsByReferenceNumber",
                "variables": {"referenceNumber": "S123456"},
            },
            {"data": {"guestShipmentSearch": None}},
            "S123456",
        )
        self.assertTrue(result["no_result"])
        self.assertEqual("No result", result["status"])

    def test_s_ocean_query_without_ei_credentials_reports_login_requirement(self):
        page = mock.Mock()
        with mock.patch.object(ei, "EI_LOGIN_ENABLED", False):
            result = ei.query_expeditors_one(page, "S123456", save_pdf=False)
        self.assertEqual("Error", result["status"])
        self.assertIn("配置 EI 邮箱和密码", result["error"])
        page.goto.assert_not_called()

    def test_dashboard_submit_clicks_real_track_button_not_guessed_coordinates(self):
        input_box = mock.Mock()
        button = mock.Mock()
        page = mock.Mock()
        page.locator.side_effect = lambda selector: (
            mock.Mock(count=mock.Mock(return_value=1), nth=mock.Mock(return_value=button))
            if selector == "button:has-text('TRACK')"
            else mock.Mock(count=mock.Mock(return_value=0))
        )
        button.is_visible.return_value = True
        button.inner_text.return_value = "TRACK"
        button.get_attribute.return_value = ""
        with mock.patch.object(ei.time, "sleep"):
            self.assertTrue(ei.click_track_submit_button(page, input_box))
        button.click.assert_called_once()
        input_box.press.assert_not_called()

    def test_dashboard_submit_clicks_unlabeled_expeditors_arrow(self):
        input_box = mock.Mock()
        arrow = mock.Mock()
        arrow.is_visible.return_value = True
        page = mock.Mock()
        page.locator.side_effect = lambda selector: (
            mock.Mock(count=mock.Mock(return_value=1), nth=mock.Mock(return_value=arrow))
            if selector == "button[type='submit'].arrow-authenticated:visible"
            else mock.Mock(count=mock.Mock(return_value=0))
        )
        with mock.patch.object(ei.time, "sleep"):
            self.assertTrue(ei.click_track_submit_button(page, input_box))
        arrow.click.assert_called_once()
        input_box.press.assert_not_called()

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

    def test_s_query_uses_status_from_matching_graphql_request(self):
        page = mock.Mock()
        page.locator.return_value.inner_text.return_value = "Shipment results"
        request = mock.Mock()
        request.post_data_json = {
            "operationName": "guestSearchShipmentsByReferenceNumber",
            "variables": {"referenceNumber": "S915237776"},
        }
        response = mock.Mock()
        response.url = "https://go2expo.expeditors.com/graphql"
        response.request = request
        response.status = 200
        response.json.return_value = {
            "data": {
                "guestShipmentSearch": {
                    "status": {
                        "description": "Services Completed: Notified Customers Broker",
                        "lastStatusChangeEvent": {
                            "description": "Shipment Turned Over",
                            "formattedDate": "12-Oct-2026",
                        },
                    }
                }
            }
        }
        callbacks = {}

        def capture_listener(_event, listener):
            callbacks["listener"] = listener

        def open_page(_page, _tracking_number, result_ready=None):
            callbacks["listener"](response)
            self.assertTrue(result_ready())
            return True

        page.on.side_effect = capture_listener
        with mock.patch.object(ei, "EI_LOGIN_ENABLED", True), \
             mock.patch.object(ei, "open_expeditors_detail_page", side_effect=open_page), \
             mock.patch.object(ei, "close_expo_welcome_popup_once"), \
             mock.patch.object(ei, "remove_overlays"):
            result = ei.query_expeditors_one(page, "S915237776", save_pdf=False)

        self.assertEqual("Services Completed", result["status"])
        self.assertFalse(result["is_delivered"])
        page.remove_listener.assert_called_once_with("response", callbacks["listener"])


if __name__ == "__main__":
    unittest.main()
