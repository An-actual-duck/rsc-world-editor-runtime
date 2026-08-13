#!/usr/bin/env python3
"""Regression coverage for non-recursive adaptive definition CSV validation."""

from __future__ import annotations

import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CORE = ROOT / "server/core.jar"


HARNESS = r"""
import com.openrsc.server.content.worldedit.AdaptiveWorldBuilderRuntimeIdentity;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

public final class AdaptiveIdListValidationFixture {
    private static final int MAX_CHARACTERS = 65536 * 11 - 1;
    private static final Method CHECKED;

    static {
        try {
            CHECKED = AdaptiveWorldBuilderRuntimeIdentity.class
                .getDeclaredMethod("checkedIdList", String.class);
            CHECKED.setAccessible(true);
        } catch (Exception failure) {
            throw new RuntimeException(failure);
        }
    }

    public static void main(String[] args) throws Exception {
        accept(null);
        accept("");
        accept("0");
        accept("00,001,000000000000000000000000000000000000000000000002");

        productionRange(214);
        productionRange(1332);
        productionRange(845);
        productionRange(3309);

        reject(",");
        reject(",0");
        reject("0,");
        reject("0,,1");
        reject("0 1");
        reject("0, 1");
        reject("+0");
        reject("-0");
        reject("0.1");
        reject("0\n1");
        reject("0\r1");
        reject("0=1");
        reject("０");
        reject("a");
        reject(zeros(MAX_CHARACTERS + 1));
    }

    private static String zeros(int count) {
        char[] value = new char[count];
        java.util.Arrays.fill(value, '0');
        return new String(value);
    }

    private static void productionRange(int count) throws Exception {
        StringBuilder value = new StringBuilder();
        for (int id = 0; id < count; id++) {
            if (value.length() > 0) value.append(',');
            value.append(id);
        }
        accept(value.toString());
    }

    private static void accept(String value) throws Exception {
        Object result = CHECKED.invoke(null, new Object[] {value});
        String expected = value == null ? "" : value;
        if (!expected.equals(result)) {
            throw new AssertionError("accepted inventory was not preserved exactly");
        }
    }

    private static void reject(String value) throws Exception {
        try {
            CHECKED.invoke(null, value);
            throw new AssertionError("invalid inventory was accepted: " + value);
        } catch (InvocationTargetException expected) {
            if (!(expected.getCause() instanceof IllegalArgumentException)) {
                throw expected;
            }
        }
    }
}
"""


class AdaptiveIdListValidationTest(unittest.TestCase):
    def test_exact_csv_grammar_is_linear_at_production_cardinalities(self) -> None:
        self.assertTrue(CORE.is_file(), "build the server before running CSV coverage")
        with tempfile.TemporaryDirectory(prefix="adaptive-id-list-") as temporary:
            directory = Path(temporary)
            source = directory / "AdaptiveIdListValidationFixture.java"
            source.write_text(textwrap.dedent(HARNESS), encoding="utf-8")
            compiled = subprocess.run(
                [
                    "javac", "-source", "8", "-target", "8",
                    "-cp", str(CORE), "-d", str(directory), str(source),
                ],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(0, compiled.returncode, compiled.stdout + compiled.stderr)
            executed = subprocess.run(
                [
                    "java", "-Xss256k", "-cp", f"{directory}:{CORE}",
                    "AdaptiveIdListValidationFixture",
                ],
                cwd=ROOT, capture_output=True, text=True,
            )
            self.assertEqual(0, executed.returncode, executed.stdout + executed.stderr)


if __name__ == "__main__":
    unittest.main()
