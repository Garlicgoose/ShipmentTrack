import tempfile
import unittest
from pathlib import Path
from unittest import mock

import units


class ResourcePathTests(unittest.TestCase):
    def test_development_resources_use_project_directory(self):
        with mock.patch.object(units.sys, "frozen", False, create=True):
            self.assertEqual(Path(units.__file__).resolve().parent, units.get_resource_path())

    def test_frozen_resources_use_meipass_but_writable_base_uses_exe_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            resource_root = Path(temp_dir) / "internal"
            executable = Path(temp_dir) / "Shipment Track.exe"
            with mock.patch.object(units.sys, "frozen", True, create=True), \
                 mock.patch.object(units.sys, "_MEIPASS", str(resource_root), create=True), \
                 mock.patch.object(units.sys, "executable", str(executable)):
                self.assertEqual(resource_root.resolve(), units.get_resource_path())
                self.assertEqual(executable.parent.resolve(), units.get_base_path())
                self.assertEqual(
                    executable.parent.resolve() / "data",
                    units.get_data_path(),
                )


if __name__ == "__main__":
    unittest.main()
