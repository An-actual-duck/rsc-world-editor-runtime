#!/usr/bin/env python3
"""Focused authoring-only settings, scale persistence and removed-UI contracts."""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JAR = ROOT / "Client_Base/Open_RSC_Client.jar"
FIXTURE = r'''
package orsc;
import java.awt.event.KeyEvent;
import java.util.Arrays;
import java.util.Properties;
public class WorldBuilderPreservationUiFixture {
    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }
    public static void main(String[] args) {
        System.setProperty(WorldBuilderUiProfile.PROPERTY, "true");
        check(!WorldBuilderUiProfile.isEnabled(), "profile leaked into player launch");
        check(RenderSurfaceSettings.getWidth() == 960, "player default changed");
        SpellbookLayoutSettings.setMode(SpellbookLayoutSettings.Mode.TEXT);
        check(SpellbookLayoutSettings.usesTextLayout(), "player spellbook changed");
        System.setProperty("openrsc.worldBuilderMode", "true");
        check(WorldBuilderUiProfile.isEnabled(), "authoring profile missing");
        check(RenderSurfaceSettings.getWidth() == 640 && RenderSurfaceSettings.getHeight() == 480,
              "existing editor dock must fit in resizable logical surface");
        check(!SpellbookLayoutSettings.usesTextLayout(), "non-Preservation spellbook exposed");
        check(!orsc.remastered.RemasteredSpriteSettings.isEnabled(), "remastered sprites exposed");
        check(WorldBuilderUiProfile.settingsTab(0) == 0 && WorldBuilderUiProfile.settingsTab(97) == 0
            && WorldBuilderUiProfile.settingsTab(98) == 1 && WorldBuilderUiProfile.settingsTab(195) == 1,
            "two-tab hit bounds mismatch");
        check(ClientHotkeySettings.shouldSuppressFunctionKey(KeyEvent.VK_F6), "dead renderer shortcut");
        LegacySoftwareScalingSettings.configureAllowedScalars(3);
        Properties settings = new Properties();
        settings.setProperty("scaling_type", "2");
        settings.setProperty("ui_scale", "1.5");
        LegacySoftwareScalingSettings.loadFromClientSettings(settings);
        check(LegacySoftwareScalingSettings.getScalingAlgorithm() == ScaledWindow.ScalingAlgorithm.INTEGER_SCALING,
              "authoring must use integer scaling even with old interpolation settings");
        check(LegacySoftwareScalingSettings.getAllowedScalars().equals(Arrays.asList(1f, 2f)), "x1/x2 choices");
        LegacySoftwareScalingSettings.applyPendingScalar(1f);
        LegacySoftwareScalingSettings.SettingsStore store = new LegacySoftwareScalingSettings.SettingsStore() {
            public Properties load() { return settings; }
            public void save(Properties value) { check(value == settings, "settings loss"); }
        };
        LegacySoftwareScalingSettings.scaleUp(store);
        check("2.0".equals(settings.getProperty("ui_scale")), "x2 not persisted");
        LegacySoftwareScalingSettings.applyPendingScalar(2f);
        check(LegacySoftwareScalingSettings.scaleDimension(640) == 1280, "x2 output width");
        check(LegacySoftwareScalingSettings.scaleDimension(480) == 960, "x2 output height");
        check(LegacySoftwareScalingSettings.unscaleCoordinate(940) == 470, "x2 input mapping");
        LegacySoftwareScalingSettings.scaleDown(store);
        check("1.0".equals(settings.getProperty("ui_scale")), "x1 not persisted");
        check(DesktopMiddleMouseSettings.usesTilt(), "middle-mouse pitch default lost");
        check(RendererExperimentalSettings.isExtraZoomEnabled(), "extended zoom lost");
        check(RendererExperimentalSettings.isCameraTiltEnabled(), "camera tilt lost");
        System.clearProperty("openrsc.worldBuilderMode");
        check(RenderSurfaceSettings.getWidth() == 960 && SpellbookLayoutSettings.usesTextLayout(),
              "authoring changed saved player presentation");
        System.out.println("PASS authoring-only Preservation UI and x1/x2 settings");
    }
}
'''


def main():
    client = (ROOT / "Client_Base/src/orsc/mudclient.java").read_text()
    general = client.split("private void drawGeneralSettingsOptions", 1)[1].split("private RendererSettingsPanel.PanelView", 1)[0]
    assert "Scaling - @gre@" in general and "Middle mouse - " in general
    assert "(isAndroid() || WorldBuilderUiProfile.isEnabled()) && S_SHOW_ROOF_TOGGLE" in general
    assert "(isAndroid() || WorldBuilderUiProfile.isEnabled()) && S_SHOW_UNDERGROUND_FLICKER_TOGGLE" in general
    assert "this.settingTab = WorldBuilderUiProfile.settingsTab(var3)" in client
    assert "WorldBuilderUiProfile.isEnabled() && this.settingTab == 2" in client
    with tempfile.TemporaryDirectory(prefix="builder-preservation-ui-") as temp:
        source = Path(temp) / "WorldBuilderPreservationUiFixture.java"
        source.write_text(FIXTURE)
        subprocess.run(["javac", "-source", "8", "-target", "8", "-cp", str(JAR), "-d", temp, str(source)], check=True)
        subprocess.run(["java", "-Djava.awt.headless=true", "-cp", temp + ":" + str(JAR), "orsc.WorldBuilderPreservationUiFixture"], check=True)


if __name__ == "__main__":
    main()
