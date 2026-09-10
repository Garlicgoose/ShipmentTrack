import unittest
from unittest import mock

from modules import dsv_module, ei_module, ups_module
from modules.tracking_utils import TrackingCarrierSession


class FakeLocator:
    def __init__(self, text):
        self.text = text

    def inner_text(self, timeout=None):
        return self.text


class FakePage:
    def __init__(self, text="Delivered"):
        self.text = text

    def goto(self, *args, **kwargs):
        return None

    def locator(self, selector):
        return FakeLocator(self.text)


class PodPolicyTests(unittest.TestCase):
    def test_ups_status_only_skips_pdf(self):
        page = FakePage()
        with mock.patch.object(ups_module, "wait_page_ready"), \
             mock.patch.object(ups_module, "close_cookie_popup"), \
             mock.patch.object(ups_module, "close_ups_assistant"), \
             mock.patch.object(ups_module, "extract_status", return_value="Delivered"), \
             mock.patch.object(ups_module, "extract_arrival_time", return_value="2026/9/10"), \
             mock.patch.object(ups_module, "save_ups_pdf") as save:
            result = ups_module.query_ups_one(page, "1Z123", save_pdf=False)
        self.assertTrue(result["is_delivered"])
        self.assertEqual("", result["pdf_file"])
        save.assert_not_called()

    def test_dsv_status_only_keeps_detail_time_but_skips_pdf(self):
        page = FakePage()
        with mock.patch.object(dsv_module, "search_dsv_tracking"), \
             mock.patch.object(dsv_module, "extract_status_from_text", return_value="Completed"), \
             mock.patch.object(dsv_module, "extract_arrival_from_search_result", return_value="2026/9/10"), \
             mock.patch.object(dsv_module, "click_dsv_shipment_result", return_value=True), \
             mock.patch.object(dsv_module, "extract_arrival_from_details", return_value="2026/9/11"), \
             mock.patch.object(dsv_module, "save_dsv_pdf") as save:
            result = dsv_module.query_dsv_one(page, "S123", save_pdf=False)
        self.assertTrue(result["is_delivered"])
        self.assertEqual("2026/9/11", result["arrival_time"])
        save.assert_not_called()

    def test_ei_status_only_skips_pdf(self):
        page = FakePage()
        with mock.patch.object(ei_module, "open_expeditors_detail_page"), \
             mock.patch.object(ei_module, "close_expo_welcome_popup_once"), \
             mock.patch.object(ei_module, "remove_overlays"), \
             mock.patch.object(ei_module, "extract_status", return_value="Completed"), \
             mock.patch.object(ei_module, "get_arrival_time", return_value="2026/9/10"), \
             mock.patch.object(ei_module, "is_expeditors_delivered", return_value=True), \
             mock.patch.object(ei_module, "save_expeditors_pdf") as save:
            result = ei_module.query_expeditors_one(page, "123", save_pdf=False)
        self.assertTrue(result["is_delivered"])
        self.assertEqual("", result["pdf_file"])
        save.assert_not_called()

    def test_carrier_session_does_not_retry_internal_type_error(self):
        query = mock.Mock(side_effect=TypeError("internal parsing bug"))
        session = object.__new__(TrackingCarrierSession)
        session.page = object()
        session.module = mock.Mock(query_one=query)
        session.config = {"query_func": "query_one", "module": "fake"}
        session.save_pdf = False
        session._cleanup_overlays = mock.Mock()

        with self.assertRaisesRegex(TypeError, "internal parsing bug"):
            session.query_one("123")
        query.assert_called_once_with(session.page, "123", save_pdf=False)


if __name__ == "__main__":
    unittest.main()
