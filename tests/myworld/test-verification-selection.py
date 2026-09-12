#!/usr/bin/env python3
"""Check runner routing using stub commands, never build or launch a runtime."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class VerificationSelectionTest(unittest.TestCase):
    def test_presentation_full_invalid_and_failure_routing(self):
        with tempfile.TemporaryDirectory(prefix="runtime-selection-") as temporary:
            root = Path(temporary)
            (root / "scripts").mkdir()
            (root / "bin").mkdir()
            (root / "tests/myworld").mkdir(parents=True)
            shutil.copy2(ROOT / "scripts/test.sh", root / "scripts/test.sh")
            python = root / "bin/python3"
            python.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$TRACE"\n'
                              'test -z "$FAIL_TEST"\n')
            python.chmod(0o755)
            full = root / "tests/myworld/test-all.sh"
            full.write_text('#!/bin/sh\nprintf "full\\n" >> "$TRACE"\n')
            full.chmod(0o755)
            trace = root / "trace"
            env = {**os.environ, "ROOT_DIR": str(root), "TRACE": str(trace),
                   "FAIL_TEST": "", "PATH": str(root / "bin") + os.pathsep + os.environ["PATH"]}
            def run(*args, fail=False):
                trace.write_text("")
                result = subprocess.run(["bash", str(root / "scripts/test.sh"), *args],
                    env={**env, "FAIL_TEST": "1" if fail else ""}, capture_output=True, text=True)
                return result.returncode, trace.read_text().splitlines()
            code, calls = run("--group", "presentation")
            self.assertEqual(0, code)
            self.assertEqual([
                "tests/myworld/test-opengl-window-viewport-extraction.py",
                "tests/myworld/test-widescreen-world-input-viewport.py",
                "tests/myworld/test-legacy-software-scaling-settings.py",
                "tests/myworld/test-world-builder-preservation-ui.py",
                "tests/myworld/test-software-editor-overlays.py"], calls)
            for args in ((), ("--full",)):
                self.assertEqual((0, ["full"]), run(*args))
            for args in (("--group", "unknown"), ("--full", "extra"), ("--unknown",)):
                self.assertEqual((2, []), run(*args))
            self.assertEqual((0, []), run("--help"))
            code, failed_calls = run("--group", "presentation", fail=True)
            self.assertNotEqual(0, code)
            self.assertEqual(calls[:1], failed_calls)


if __name__ == "__main__":
    unittest.main()
