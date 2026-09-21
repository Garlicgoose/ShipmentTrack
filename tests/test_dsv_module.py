import unittest
from unittest import mock

from modules import dsv_module as dsv


class DsvNavigationTests(unittest.TestCase):
    @mock.patch("modules.dsv_module.time.sleep", return_value=None)
    @mock.patch("modules.dsv_module.wait_page_ready", return_value=None)
    def test_direct_result_href_does_not_require_matching_shipment_id(self, _ready, _sleep):
        link = mock.Mock()
        link.get_attribute.return_value = "/new/tracking/shipment-details-public/34490022345862"
        links = mock.Mock()
        links.count.return_value = 1
        links.nth.return_value = link
        page = mock.Mock()
        page.url = "https://mydsv.com/new/tracking/track-shipment"
        page.locator.return_value = links
        with mock.patch.object(dsv, "is_dsv_detail_page", return_value=True):
            self.assertTrue(dsv.navigate_dsv_details_by_link(page))
        target = page.goto.call_args.args[0]
        self.assertIn("shipment-details-public/34490022345862", target)

    @mock.patch("modules.dsv_module.time.sleep", return_value=None)
    @mock.patch("modules.dsv_module.wait_page_ready", return_value=None)
    def test_position_click_is_used_when_identifiers_do_not_match(self, _ready, _sleep):
        item = mock.Mock()
        item.is_visible.return_value = True
        item.bounding_box.return_value = {"x": 100, "y": 200, "width": 500, "height": 100}
        items = mock.Mock()
        items.count.return_value = 1
        items.nth.return_value = item
        page = mock.Mock()
        page.locator.return_value = items
        with mock.patch.object(dsv, "is_dsv_detail_page", return_value=True):
            self.assertTrue(dsv.click_dsv_result_by_position(page))
        page.mouse.click.assert_called_once()

    @mock.patch("modules.dsv_module.time.sleep", return_value=None)
    @mock.patch("modules.dsv_module.wait_page_ready", return_value=None)
    def test_current_dsv_cursor_card_is_a_position_fallback(self, _ready, _sleep):
        empty = mock.Mock()
        empty.count.return_value = 0
        card = mock.Mock()
        card.is_visible.return_value = True
        card.inner_text.return_value = "Shipment ID\n34490022435862\nStatus\nCompleted"
        card.bounding_box.return_value = {"x": 130, "y": 470, "width": 1190, "height": 188}
        cards = mock.Mock()
        cards.count.return_value = 1
        cards.nth.return_value = card
        page = mock.Mock()
        page.locator.side_effect = lambda selector: (
            cards if selector == "[class*='cursor-pointer']" else empty
        )
        with mock.patch.object(dsv, "is_dsv_detail_page", return_value=True):
            self.assertTrue(dsv.click_dsv_result_by_position(page))
        page.mouse.click.assert_called_once()

    @mock.patch("modules.dsv_module.time.sleep", return_value=None)
    @mock.patch("modules.dsv_module.wait_page_ready", return_value=None)
    def test_clicks_visible_result_id_even_when_it_differs_from_query(self, _ready, _sleep):
        empty = mock.Mock()
        empty.count.return_value = 0
        result_id = mock.Mock()
        result_id.is_visible.return_value = True
        result_id.inner_text.return_value = "34490022435862"
        result_id.bounding_box.return_value = {"x": 135, "y": 502, "width": 109, "height": 16}
        links = mock.Mock()
        links.count.return_value = 1
        links.nth.return_value = result_id
        page = mock.Mock()
        page.locator.side_effect = lambda selector: (
            links if selector == "a[class*='cursor-pointer']" else empty
        )
        with mock.patch.object(dsv, "is_dsv_detail_page", return_value=True):
            self.assertTrue(dsv.click_dsv_result_by_position(page))
        page.mouse.click.assert_called_once()

    def test_detail_page_can_be_confirmed_by_content_when_url_shape_changes(self):
        page = mock.Mock()
        page.url = "https://mydsv.com/new/tracking/view/opaque"
        page.locator.return_value.inner_text.return_value = "Summary\nShipment Progress\nCompleted"
        self.assertTrue(dsv.is_dsv_detail_page(page))

    def test_wait_for_status_keeps_polling_until_card_renders(self):
        """回归：结果卡片比 “Showing N results” 晚渲染时不能直接判 Unknown。"""
        page = mock.Mock()
        page.locator.return_value.inner_text.side_effect = [
            "Showing 1 of 1 results Shipment ID SMFM0013890 Status",
            "Showing 1 of 1 results Status Completed Actual delivery 08-Sep-2026 15:00",
        ]
        status, text = dsv.wait_for_status(page, attempts=5, delay=0)
        self.assertEqual("Completed", status)
        self.assertIn("08-Sep-2026", text)

    def test_wait_for_status_reports_unknown_after_retries(self):
        page = mock.Mock()
        page.locator.return_value.inner_text.return_value = "Showing 1 of 1 results Status"
        status, _text = dsv.wait_for_status(page, attempts=3, delay=0)
        self.assertEqual("Unknown", status)
        self.assertEqual(3, page.locator.return_value.inner_text.call_count)

    def test_query_dsv_one_rerenders_status_before_giving_up(self):
        page = mock.Mock()
        page.locator.return_value.inner_text.side_effect = [
            "Showing 1 of 1 results Status",  # 第一次读不到状态
            "Showing 1 of 1 results Status Completed",  # 轮询后读到
        ]
        page.url = "https://mydsv.com/new/tracking/track-shipment"
        with mock.patch.object(dsv, "search_dsv_tracking"), \
             mock.patch.object(dsv, "wait_for_status", wraps=dsv.wait_for_status) as wait, \
             mock.patch.object(dsv, "click_dsv_shipment_result", return_value=False):
            result = dsv.query_dsv_one(page, "SMFM0013890", save_pdf=False)
        self.assertEqual("Completed", result["status"])
        self.assertTrue(result["is_delivered"])
        wait.assert_called_once()

    def test_extract_status_recognizes_in_progress(self):
        """回归：DSV 结果卡里 “In Progress” 之前没进关键词表，被判 Unknown。"""
        self.assertEqual(
            "In Progress",
            dsv.extract_status_from_text("Showing 1 of 1 results Status In Progress"),
        )


if __name__ == "__main__":
    unittest.main()
