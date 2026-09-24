#!/usr/bin/env python3
"""Exercise actual terrain-browser open/input paths with an adaptive profile.

The fixture installs in-memory session inventories, avoiding any user project,
server, display, or authentication state. Each scenario uses a fresh JVM so the
catalog's startup cache sees the intended stock/custom/malformed inventory.
"""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JAR = ROOT / 'Client_Base/Open_RSC_Client.jar'
SOURCE = r'''
package com.openrsc.interfaces.misc;
import com.openrsc.client.entityhandling.EntityHandler;
import com.openrsc.client.entityhandling.defs.DoorDef;
import com.openrsc.client.entityhandling.defs.TileDef;
import orsc.AdaptiveWorldBuilderClientSession;
import orsc.WorldBuilderClientProfile;
import orsc.mudclient;
import java.lang.reflect.*;
import java.util.List;
import sun.misc.Unsafe;

public class ProjectTerrainBrowserFixture {
    static void require(boolean ok, String message) { if (!ok) throw new AssertionError(message); }
    static Field field(Class<?> type, String name) throws Exception {
        Field f=type.getDeclaredField(name); f.setAccessible(true); return f;
    }
    static Object invoke(Object target, String name, Class<?>[] types, Object... args) throws Exception {
        Method m=target.getClass().getDeclaredMethod(name,types); m.setAccessible(true);
        try { return m.invoke(target,args); }
        catch (InvocationTargetException e) { throw new AssertionError(name + " failed",e.getCause()); }
    }
    public static void main(String[] args) throws Exception {
        EntityHandler.load(true);
        Unsafe unsafe=(Unsafe)field(Unsafe.class,"theUnsafe").get(null);
        int tile=10, wall=8;
        boolean malformed=args[0].equals("malformed");
        if (!args[0].equals("stock")) {
            List<DoorDef> doors=(List<DoorDef>)field(EntityHandler.class,"doors").get(null);
            wall=doors.size();
            doors.add(new DoorDef("Fixture crystal wall", null, null, null, 1,0,128,-1,-1,wall));
            List<TileDef> tiles=(List<TileDef>)field(EntityHandler.class,"tiles").get(null);
            tile=tiles.size(); tiles.add(new TileDef(-1,0,0));
            if (malformed) {
                tiles.set(1,null);
                doors.add(null);
                doors.add(new DoorDef(" ",null,null,null,0,0,0,0,0,doors.size()));
            }
        }
        AdaptiveWorldBuilderClientSession session=(AdaptiveWorldBuilderClientSession)
            unsafe.allocateInstance(AdaptiveWorldBuilderClientSession.class);
        field(session.getClass(),"authorableFloorIds").set(session,new int[]{1,tile});
        field(session.getClass(),"authorableBoundaryIds").set(session,new int[]{wall});
        WorldBuilderClientProfile profile=(WorldBuilderClientProfile)
            unsafe.allocateInstance(WorldBuilderClientProfile.class);
        field(profile.getClass(),"enabled").set(profile,true);
        field(profile.getClass(),"adaptive").set(profile,true);
        field(profile.getClass(),"adaptiveSession").set(profile,session);
        field(profile.getClass(),"current").set(null,profile);
        // The profile contract must stay strict: fix callers, do not accept typos.
        try { profile.definitionIds("floor"); throw new AssertionError("unknown family accepted"); }
        catch (IllegalArgumentException expected) { }
        WorldEditorInterface editor=new WorldEditorInterface((mudclient)unsafe.allocateInstance(mudclient.class));
        WorldEditorDefinitionBrowser browser=(WorldEditorDefinitionBrowser)
            field(editor.getClass(),"definitionBrowser").get(editor);
        invoke(editor,"openFloorBrowser",new Class<?>[]{});
        require(browser.isOpen(),"floor did not open");
        require(browser.resultCount()==(malformed?3:5),"floor inventory/aliases wrong");
        browser.setQuery("#"+(tile+1));
        require(browser.resultCount()==1,"floor custom/stock ID absent");
        invoke(editor,"handleDefinitionBrowserKey",new Class<?>[]{char.class,int.class},'\n',13);
        require(!browser.isOpen(),"floor selection did not close");
        require(field(editor.getClass(),"terrainFloorTexture").getInt(editor)==tile+1,"floor ID changed");
        for (int fieldId : new int[]{10,11,12,18}) {
            invoke(editor,"openWallBrowser",new Class<?>[]{int.class},fieldId);
            require(browser.resultCount()==1,"wall project inventory wrong");
            browser.setQuery(args[0].equals("stock")?"gray bricks":"crystal");
            require(browser.resultCount()==1,"wall metadata not searchable");
            invoke(editor,"handleDefinitionBrowserMouse",new Class<?>[]{int.class,int.class,int.class},15,105,1);
            require(!browser.isOpen(),"wall mouse selection did not close");
            require((Integer)invoke(editor,"terrainWallValue",new Class<?>[]{int.class},fieldId)==wall+1,
                "wall selection did not preserve one-based raw ID");
        }
        invoke(editor,"openWallBrowser",new Class<?>[]{int.class},10);
        browser.setQuery("#99999"); require(browser.resultCount()==0,"filter escaped inventory");
        invoke(editor,"handleDefinitionBrowserKey",new Class<?>[]{char.class,int.class},(char)27,27);
        require(!browser.isOpen(),"escape did not close");
        invoke(editor,"openFloorBrowser",new Class<?>[]{});
        invoke(editor,"handleDefinitionBrowserMouse",new Class<?>[]{int.class,int.class,int.class},371,10,1);
        require(!browser.isOpen(),"close button did not close");
    }
}
'''

class ProjectTerrainBrowserTest(unittest.TestCase):
    def test_project_terrain_browser_input_paths(self):
        self.assertTrue(JAR.is_file(), 'build client first')
        with tempfile.TemporaryDirectory(prefix='project-terrain-browser-') as tmp:
            source=Path(tmp)/'ProjectTerrainBrowserFixture.java'
            source.write_text(SOURCE)
            result=subprocess.run(['javac','-cp',str(JAR),'-d',tmp,str(source)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            for scenario in ('stock','custom','malformed'):
                with self.subTest(scenario=scenario):
                    result=subprocess.run(['java','-Djava.awt.headless=true','-cp',os.pathsep.join((tmp,str(JAR))),
                        'com.openrsc.interfaces.misc.ProjectTerrainBrowserFixture',scenario],cwd=ROOT,
                        capture_output=True,text=True)
                    self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                    if scenario=='malformed':
                        self.assertIn('Skipping tile #1',result.stderr)
                        self.assertIn('Skipping boundary #',result.stderr)
                        self.assertIn('Check the selected content provider',result.stderr)

if __name__=='__main__': unittest.main()
