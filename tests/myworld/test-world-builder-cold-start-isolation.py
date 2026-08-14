#!/usr/bin/env python3
"""Focused guards for adaptive cold-start framing and database-log closure."""

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "server/core.jar"


HARNESS = r"""
import com.openrsc.server.database.impl.mysql.ScriptRunner;
import com.openrsc.server.net.RSCSessionIdSender;
import java.io.File;

public final class WorldBuilderColdStartIsolationHarness {
    private static void require(boolean value, String message) {
        if (!value) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        require(!RSCSessionIdSender.shouldSchedule(true, true),
            "adaptive World Builder must not send unsolicited legacy bytes");
        require(RSCSessionIdSender.shouldSchedule(false, false),
            "ordinary runtime keeps legacy compatibility timer");
        require(RSCSessionIdSender.shouldSchedule(true, false),
            "non-adaptive World Builder keeps legacy compatibility timer");
        require(RSCSessionIdSender.shouldSchedule(false, true),
            "adaptive flag alone does not alter ordinary runtime");

        new ScriptRunner(null, false, true);
        require(!new File("create_db.log").exists(),
            "database output must not escape to runtime root");
        require(!new File("create_db_error.log").exists(),
            "database errors must not escape to runtime root");
        require(new File("logs/create_db.log").isFile(),
            "database output belongs in designated logs directory");
        require(new File("logs/create_db_error.log").isFile(),
            "database errors belong in designated logs directory");
    }
}
"""


class WorldBuilderColdStartIsolationTest(unittest.TestCase):
    def test_session_policy_and_database_log_location(self):
        self.assertTrue(CORE.is_file(), "run ./scripts/build-server.sh first")
        with tempfile.TemporaryDirectory(
            prefix="world-builder-cold-start-isolation-"
        ) as temp:
            root = Path(temp)
            source = root / "WorldBuilderColdStartIsolationHarness.java"
            source.write_text(textwrap.dedent(HARNESS), encoding="utf-8")
            subprocess.run(
                ["javac", "-source", "8", "-target", "8", "-cp", str(CORE),
                 "-d", str(root), str(source)],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            result = subprocess.run(
                ["java", "-cp", str(CORE) + ":" + str(root),
                 "WorldBuilderColdStartIsolationHarness"],
                cwd=root, capture_output=True, text=True,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
