import unittest

from modules import dsv_module, ei_module
from modules.status_rules import matches_exact_status, normalize_status


class StatusRuleTests(unittest.TestCase):
    def tearDown(self):
        dsv_module.CUSTOM_DELIVERED_STATUSES = ()
        ei_module.CUSTOM_DELIVERED_STATUSES = ()

    def test_status_normalization_is_strict_after_whitespace_cleanup(self):
        self.assertEqual("交给其他清关人", normalize_status(" 交给其他清关人。 "))
        self.assertTrue(matches_exact_status("Delivered.", ("Delivered",)))
        self.assertFalse(
            matches_exact_status("Delivered to service point", ("Delivered",))
        )

    def test_dsv_accepts_custom_exact_status(self):
        dsv_module.CUSTOM_DELIVERED_STATUSES = ("交给其他清关人",)
        self.assertTrue(dsv_module.is_dsv_delivered("交给其他清关人"))
        self.assertFalse(dsv_module.is_dsv_delivered("已交给其他清关人处理"))

    def test_ei_accepts_custom_exact_status(self):
        ei_module.CUSTOM_DELIVERED_STATUSES = ("Customs handoff",)
        self.assertTrue(ei_module.is_expeditors_delivered("Customs handoff", ""))
        self.assertFalse(
            ei_module.is_expeditors_delivered("Customs handoff pending", "")
        )


if __name__ == "__main__":
    unittest.main()
