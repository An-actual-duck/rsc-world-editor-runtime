#!/usr/bin/env python3
"""Camera-only projection regression; software overlays must not fabricate captured frames."""
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JAR = ROOT / "Client_Base/Open_RSC_Client.jar"
FIXTURE = r'''
import java.lang.reflect.Field;
import java.util.Arrays;
import orsc.graphics.three.Scene;
import orsc.graphics.three.WorldEditorProjection;
import sun.misc.Unsafe;
public class SoftwareEditorOverlayFixture {
    static void set(Scene scene, String name, int value) throws Exception {
        Field field = Scene.class.getDeclaredField(name);
        field.setAccessible(true); field.setInt(scene, value);
    }
    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }
    public static void main(String[] args) throws Exception {
        Field unsafeField = Unsafe.class.getDeclaredField("theUnsafe");
        unsafeField.setAccessible(true);
        Scene scene = (Scene)((Unsafe)unsafeField.get(null)).allocateInstance(Scene.class);
        set(scene, "rot1024_off_x", 1234); set(scene, "rot1024_off_y", -700);
        set(scene, "rot1024_off_z", 3456); set(scene, "m_Zb", 320); set(scene, "m_Nb", 240);
        set(scene, "rot1024_vp_src", 9);
        int[] direct = new int[2], software = new int[2];
        check(WorldEditorProjection.project(10,20,100,0,0,0,0,0,0,320,240,8,5,direct)
            && Arrays.equals(direct,new int[]{345,291}), "known software screen coordinates");
        check(!WorldEditorProjection.project(0,0,4,0,0,0,0,0,0,320,240,8,5,direct), "near clipping");
        for (int pitch : new int[]{0,64,128,256,960}) for (int yaw : new int[]{0,128,256,512,896}) {
            set(scene,"cameraProjX",pitch); set(scene,"cameraProjY",yaw); set(scene,"cameraProjZ",0);
            for(int x=500;x<2200;x+=400) for(int z=2500;z<5000;z+=400) {
                boolean a=WorldEditorProjection.project(x,-20,z,1234,-700,3456,pitch,yaw,0,320,240,9,5,direct);
                boolean b=scene.projectWorldEditorPoint(x,-20,z,software);
                check(a==b && (!a || Arrays.equals(direct,software)), "live scene camera mismatch");
                check(scene.getRenderer3DFrame()==null, "projection manufactured capture/latch frame");
            }
        }
        System.out.println("PASS software camera-only editor projection and null capture");
    }
}
'''


def main():
    client = (ROOT / "Client_Base/src/orsc/mudclient.java").read_text()
    previews = client.split("private void drawWorldEditorTerrainToolPreview", 1)[1].split("private void drawWorldEditorRegionSegment", 1)[0]
    assert "frame==null" not in previews
    assert "if (frame == null) return WorldBuilderUiProfile.isEnabled() && scene != null" in client
    assert "this.completeLayeredSceneActivationFreshFrame(null, true)" in client
    assert "int cameraX=x-frame.getCameraOffsetX()" in client  # Existing captured-frame route unchanged.
    assert "int firstTabWidth = magicPanelWidth / (classicMenu ? 2 : 3)" in client
    assert "if (classicMenu && this.magicOrPrayerList > 1)" in client
    assert "if (WorldBuilderUiProfile.isEnabled() && CurrentBaseSkillContract.selected()) return;" in client
    assert "y = 48;" in client
    assert "this.showCoordinatesOverlay && (!WorldBuilderUiProfile.isEnabled() || this.showUiTab == 0)" in client
    clip_methods = client.split("private void drawWorldEditorGridLine", 1)[1].split("public void setWorldEditorBuildMode", 1)[0]
    clip_fixture = '''public class EditorOverlayClipFixture {
        static class Surface { int width2=640,height2=480; int[] pixelData=new int[640*480]; }
        final Surface surface=new Surface(); Surface getSurface(){return surface;}
        private void drawWorldEditorGridLine''' + clip_methods + '''
        public static void main(String[] args) {
            EditorOverlayClipFixture fixture=new EditorOverlayClipFixture();
            for(int extent:new int[]{1000,100000,2000000}) {
                fixture.drawWorldEditorGridLine(-extent,-extent,extent,extent,123);
                fixture.drawWorldEditorGridLine(-extent,extent,extent,-extent,123);
                fixture.drawWorldEditorGridLine(-extent,240,extent,240,123);
                fixture.drawWorldEditorGridLine(320,-extent,320,extent,123);
            }
            if(fixture.surface.pixelData[320+240*640]!=123) throw new AssertionError("clipped line missing");
            System.out.println("PASS near-plane large-coordinate grid clipping");
        }
    }'''
    with tempfile.TemporaryDirectory(prefix="software-editor-overlays-") as temp:
        source = Path(temp) / "SoftwareEditorOverlayFixture.java"
        source.write_text(FIXTURE)
        clip_source = Path(temp) / "EditorOverlayClipFixture.java"
        clip_source.write_text(clip_fixture)
        subprocess.run(["javac", "-source", "8", "-target", "8", "-cp", str(JAR), "-d", temp, str(source), str(clip_source)], check=True)
        subprocess.run(["java", "-Djava.awt.headless=true", "-cp", temp + ":" + str(JAR), "SoftwareEditorOverlayFixture"], check=True)
        subprocess.run(["java", "-cp", temp, "EditorOverlayClipFixture"], check=True, timeout=10)


if __name__ == "__main__":
    main()
