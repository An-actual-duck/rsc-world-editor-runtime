#!/usr/bin/env python3
"""Offline pinned presenter-input and built-payload refusal regressions."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("base_lwjgl", ROOT / "scripts/current-base-lwjgl.py")
LWJGL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(LWJGL)


class PresenterDependenciesTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="base-presenter-inputs-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.lib = self.root / "lib"
        LWJGL.provision(self.lib, ROOT / "PC_Client/lib/lwjgl")

    def test_pinned_offline_staging_is_complete(self):
        LWJGL.validate(self.lib)
        self.assertEqual(set(LWJGL.PINS), {path.name for path in self.lib.iterdir()})

    def test_missing_changed_extra_and_symlink_inputs_refuse(self):
        path = self.lib / "lwjgl-3.3.4.jar"
        original = path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(ValueError, "Missing/unsafe"):
            LWJGL.validate(self.lib)
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "Changed pinned"):
            LWJGL.provision(self.lib, ROOT / "PC_Client/lib/lwjgl")
        self.assertEqual(b"changed", path.read_bytes())
        path.unlink()
        path.symlink_to(ROOT / "PC_Client/lib/lwjgl/lwjgl-3.3.4.jar")
        with self.assertRaisesRegex(ValueError, "Missing/unsafe"):
            LWJGL.validate(self.lib)
        path.unlink()
        path.write_bytes(original)
        (self.lib / "lwjgl-3.3.5.jar").write_bytes(original)
        with self.assertRaisesRegex(ValueError, "Unexpected"):
            LWJGL.validate(self.lib)

    def test_archive_checks_classes_and_both_platform_native_bytes(self):
        records = LWJGL.payload(self.lib)
        for entry in ("org/lwjgl/Version.class", "org/lwjgl/glfw/GLFW.class",
                      "org/lwjgl/opengl/GL.class", "linux/x64/org/lwjgl/liblwjgl.so",
                      "windows/x64/org/lwjgl/lwjgl.dll"):
            self.assertIn(entry, records)
        archive = self.root / "client.jar"
        def write(payload):
            with zipfile.ZipFile(archive, "w") as output:
                for name, data in payload.items():
                    output.writestr(name, data)
        write(records)
        LWJGL.verify_archive(archive, self.lib)
        changed = dict(records)
        changed["windows/x64/org/lwjgl/lwjgl.dll"] = b"tampered"
        write(changed)
        with self.assertRaisesRegex(ValueError, "changed LWJGL payload"):
            LWJGL.verify_archive(archive, self.lib)
        del changed["windows/x64/org/lwjgl/lwjgl.dll"]
        write(changed)
        with self.assertRaisesRegex(ValueError, "inventory differs"):
            LWJGL.verify_archive(archive, self.lib)


if __name__ == "__main__":
    unittest.main()
