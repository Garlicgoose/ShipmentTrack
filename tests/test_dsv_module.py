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

    def test_detail_page_can_be_confirmed_by_content_when_url_shape_changes(self):
        page = mock.Mock()
        page.url = "https://mydsv.com/new/tracking/view/opaque"
        page.locator.return_value.inner_text.return_value = "Summary\nShipment Progress\nCompleted"
        self.assertTrue(dsv.is_dsv_detail_page(page))


if __name__ == "__main__":
    unittest.main()
