#!/usr/bin/env python3
"""Exercise idempotent, non-fatal plugin class-loader cleanup."""

from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import textwrap


ROOT = Path(__file__).resolve().parents[2]
LOADER = ROOT / "server/src/com/openrsc/server/plugins/io/PluginJarLoader.java"
INSTALLED_LAUNCH = ROOT / "server/src/com/openrsc/server/CurrentInstalledLaunch.java"
LOG4J_API = ROOT / "server/lib/log4j-api-2.17.0.jar"
LOG4J_CORE = ROOT / "server/lib/log4j-core-2.17.0.jar"
JSON = ROOT / "server/lib/json-20190722.jar"


def fail(message: str) -> None:
    raise SystemExit(f"FAIL: {message}")


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def main() -> None:
    source = LOADER.read_text(encoding="utf-8")
    require("catch(Exception ignored)" not in source, "class-loader close failure is still swallowed")
    require(
        "catch (final IOException failure)" in source
        and "best-effort cleanup" in source,
        "class-loader close failure lacks a bounded diagnostic",
    )
    require(
        "if (urlClassLoader == null)" in source
        and "finally" in source
        and "urlClassLoader = null;" in source,
        "class-loader cleanup is not explicitly idempotent",
    )

    javac = shutil.which("javac")
    java = shutil.which("java")
    require(javac is not None and java is not None, "Java compiler/runtime are required")
    # Compile the real bootstrap dependency; no installed context is activated
    # by this generic cleanup fixture, and no game/server classes are needed.
    classpath = os.pathsep.join((str(LOG4J_API), str(LOG4J_CORE), str(JSON)))
    harness = textwrap.dedent(
        """
        package com.openrsc.server.plugins.io;

        import java.io.IOException;
        import java.lang.reflect.Field;
        import java.net.URL;
        import java.net.URLClassLoader;

        public final class PluginJarLoaderCleanupHarness {
            private static final class FailingClassLoader extends URLClassLoader {
                private int closeCalls;

                private FailingClassLoader() {
                    super(new URL[0]);
                }

                @Override
                public void close() throws IOException {
                    closeCalls++;
                    throw new IOException("fixture close failure");
                }
            }

            private static void check(boolean condition, String message) {
                if (!condition) {
                    throw new AssertionError(message);
                }
            }

            public static void main(String[] args) throws Exception {
                PluginJarLoader loader = new PluginJarLoader();
                loader.clear();
                loader.clear();

                FailingClassLoader failing = new FailingClassLoader();
                Field field = PluginJarLoader.class.getDeclaredField("urlClassLoader");
                field.setAccessible(true);
                field.set(loader, failing);
                loader.getLoadedClasses().add(PluginJarLoaderCleanupHarness.class);

                loader.clear();
                check(loader.getLoadedClasses().isEmpty(), "loaded classes were not cleared");
                check(failing.closeCalls == 1, "failing class loader was not closed once");

                loader.clear();
                check(failing.closeCalls == 1, "repeated cleanup retried a released class loader");
            }
        }
        """
    )

    with tempfile.TemporaryDirectory(prefix="server-plugin-cleanup-") as directory:
        temp = Path(directory)
        harness_path = temp / "PluginJarLoaderCleanupHarness.java"
        harness_path.write_text(harness, encoding="utf-8")
        compile_result = subprocess.run(
            [
                javac,
                "-source",
                "8",
                "-target",
                "8",
                "-cp",
                classpath,
                "-d",
                str(temp),
                str(LOADER),
                str(INSTALLED_LAUNCH),
                str(harness_path),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        require(compile_result.returncode == 0, f"cleanup fixture compile failed:\n{compile_result.stderr}")
        run_result = subprocess.run(
            [
                java,
                "-cp",
                os.pathsep.join((str(temp), classpath)),
                "com.openrsc.server.plugins.io.PluginJarLoaderCleanupHarness",
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        require(run_result.returncode == 0, f"cleanup fixture failed:\n{run_result.stderr}")

    print("PASS: plugin class-loader cleanup is diagnostic, idempotent, and non-fatal")


if __name__ == "__main__":
    main()
