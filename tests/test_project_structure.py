import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProjectStructureTests(unittest.TestCase):
    def test_active_architecture_files_exist(self):
        expected = (
            "docs/ARCHITECTURE.md",
            "ui/main_window.py",
            "ui/settings_page.py",
            "ui/components.py",
            "modules/tracking_runner.py",
            "modules/excel_reconcile.py",
            "modules/pod_audit.py",
        )
        for relative in expected:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_retired_demo_and_dialogs_are_removed(self):
        retired = (
            "ui-demo.html",
            "tests/test_ui_demo.py",
            "ui/settings_dialog.py",
            "ui/about_dialog.py",
        )
        for relative in retired:
            self.assertFalse((ROOT / relative).exists(), relative)


if __name__ == "__main__":
    unittest.main()
