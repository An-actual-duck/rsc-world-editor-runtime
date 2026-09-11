#!/usr/bin/env python3
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "PC_Client/src/orsc/ClientHotkeySettings.java"
APPLET = ROOT / "PC_Client/src/orsc/ORSCApplet.java"
INPUT_BRIDGE = ROOT / "PC_Client/src/orsc/OpenGLInputBridge.java"
PACKAGER = ROOT / "scripts/package-player-release.sh"
BUILD_SCRIPT = ROOT / "scripts/build-client.sh"
BUILD_FILE = ROOT / "Client_Base/build.xml"
LAUNCHERS = (
    ROOT / "release/player/play-spoiled-milk.sh",
    ROOT / "release/player/Play Spoiled Milk.cmd",
    ROOT / "release/player/Play Spoiled Milk Windows.cmd",
)


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    sys.exit(1)


FIXTURE = r"""
package orsc;

import java.awt.event.KeyEvent;

public final class ClientHotkeySettingsFixture {
    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }

    public static void main(String[] args) {
        boolean release = Boolean.parseBoolean(args[0]);
        require(ClientHotkeySettings.isReleaseBuild() == release, "release mode mismatch");
        require(!ClientHotkeySettings.shouldSuppressFunctionKey(KeyEvent.VK_F6), "F6 must remain available");
        require(ClientHotkeySettings.shouldSuppressFunctionKey(KeyEvent.VK_F1) == release, "F1 guard mismatch");
        require(ClientHotkeySettings.shouldSuppressFunctionKey(KeyEvent.VK_F7) == release, "F7 guard mismatch");
        require(ClientHotkeySettings.shouldSuppressFunctionKey(KeyEvent.VK_F9) == release, "F9 guard mismatch");
        require(ClientHotkeySettings.shouldSuppressFunctionKey(KeyEvent.VK_F12) == release, "F12 guard mismatch");
        require(!ClientHotkeySettings.shouldSuppressFunctionKey(KeyEvent.VK_HOME), "non-function keys must remain available");
        require(ClientHotkeySettings.showDeveloperFunctionKeyHints() != release, "hint visibility mismatch");
        System.out.println("PASS: release function-key policy");
    }
}
"""


def run(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True)


def main() -> None:
    applet = APPLET.read_text(encoding="utf-8")
    bridge = INPUT_BRIDGE.read_text(encoding="utf-8")
    packager = PACKAGER.read_text(encoding="utf-8")
    build_script = BUILD_SCRIPT.read_text(encoding="utf-8")
    build_file = BUILD_FILE.read_text(encoding="utf-8")
    guard = "ClientHotkeySettings.shouldSuppressFunctionKey(keyCode)"
    if guard not in applet:
        fail("desktop key handler does not apply the release function-key guard")
    key_handler = applet.index("public final synchronized void keyPressed")
    if applet.index(guard, key_handler) > applet.index("mudclient.handleDesktopKeyPress", key_handler):
        fail("release function-key guard runs after general client input handling")
    if "ClientHotkeySettings.showDeveloperFunctionKeyHints()" not in applet:
        fail("release diagnostics still advertise disabled developer hotkeys")
    if "!ClientHotkeySettings.shouldSuppressFunctionKey(binding.awtKeyCode)" not in bridge:
        fail("OpenGL frame-capture hotkey bypasses the release guard")
    if 'RELEASE_MARKER_ENTRY="spoiled-milk-release-build.marker"' not in packager:
        fail("release packager does not embed a client-jar release marker")
    if 'SPOILED_MILK_RELEASE_BUILD=1 "$ROOT_DIR/scripts/build-client.sh"' not in packager:
        fail("release packager does not request a marked client build")
    if "SPOILED_MILK_RELEASE_BUILD" not in build_script or "release.marker.file" not in build_file:
        fail("client build does not support an isolated release marker")
    for launcher in LAUNCHERS:
        if "-Dspoiledmilk.releaseBuild=true" not in launcher.read_text(encoding="utf-8"):
            fail(f"release launcher is missing release mode: {launcher.name}")

    with tempfile.TemporaryDirectory(prefix="release-hotkey-guard-") as raw_tmp:
        tmp = Path(raw_tmp)
        fixture = tmp / "source/orsc/ClientHotkeySettingsFixture.java"
        fixture.parent.mkdir(parents=True)
        fixture.write_text(FIXTURE, encoding="utf-8")
        classes = tmp / "classes"
        classes.mkdir()
        compiled = run(
            ["javac", "-source", "1.8", "-target", "1.8", "-d", str(classes), str(SOURCE),
             str(ROOT / "Client_Base/src/orsc/WorldBuilderUiProfile.java"), str(fixture)],
            ROOT,
        )
        if compiled.returncode != 0:
            fail("hotkey fixture compile failed:\n" + compiled.stdout + compiled.stderr)

        developer = run(
            ["java", "-cp", str(classes), "orsc.ClientHotkeySettingsFixture", "false"],
            ROOT,
        )
        if developer.returncode != 0:
            fail("developer-mode fixture failed:\n" + developer.stdout + developer.stderr)

        release = run(
            [
                "java",
                "-Dspoiledmilk.releaseBuild=true",
                "-cp",
                str(classes),
                "orsc.ClientHotkeySettingsFixture",
                "true",
            ],
            ROOT,
        )
        if release.returncode != 0:
            fail("release-property fixture failed:\n" + release.stdout + release.stderr)

        (classes / "spoiled-milk-release-build.marker").write_text("release-build=true\n", encoding="utf-8")
        marked = run(
            ["java", "-cp", str(classes), "orsc.ClientHotkeySettingsFixture", "true"],
            ROOT,
        )
        if marked.returncode != 0:
            fail("release-marker fixture failed:\n" + marked.stdout + marked.stderr)

    print("PASS: release builds suppress non-F6 function keys and hide their hints")


if __name__ == "__main__":
    main()
