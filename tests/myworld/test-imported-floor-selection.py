#!/usr/bin/env python3
"""Resolve arbitrary extended originals through the actual client inventory."""
from pathlib import Path
import importlib.util
import subprocess
import tempfile
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('floors',ROOT/'scripts/standard-floors.py')
floors=importlib.util.module_from_spec(spec);spec.loader.exec_module(floors)
java=r'''
package com.openrsc.interfaces.misc;
import java.lang.reflect.*;import java.nio.file.*;
import com.openrsc.client.entityhandling.EntityHandler;
import com.openrsc.client.entityhandling.defs.TileDef;
public class ImportedFloorProbe {
 static void check(boolean b,String m){if(!b)throw new AssertionError(m);}
 public static void main(String[] args)throws Exception {
  Method load=EntityHandler.class.getDeclaredMethod("loadProjectTiles",Path.class);load.setAccessible(true);load.invoke(null,Paths.get(args[0]));
  WorldEditorFloorSelection.Definitions defs=new WorldEditorFloorSelection.Definitions(){public int size(){return EntityHandler.tileCount();}public TileDef get(int id){return EntityHandler.getTileDef(id);}public boolean allowed(int id){return true;}};
  for(int level:new int[]{-1,0,1,2,5})for(boolean walk:new boolean[]{false,true}) {
   int blocking=walk?0:1;
   int base=WorldEditorFloorSelection.resolve(defs,0,walk,level);check(base>0&&defs.get(base-1).usesExplicitBaseColor(),"base unavailable");
   for(int raw=1;raw<=Integer.parseInt(args[1]);raw++) {
    int selected=WorldEditorFloorSelection.resolve(defs,raw,walk,level);check(selected>0,"source unavailable");
    TileDef tile=defs.get(selected-1), original=defs.get(raw-1);
    check(tile.getObjectType()==blocking&&tile.getColour()==original.getColour()&&tile.getTileValue()==original.getTileValue(),"appearance/collision changed");
    check(selected==raw||tile.getWorldBuilderSourceOverlay()==raw,"visual source identity changed");
    if(raw==2||raw==11||original.getColour()==12345678&&original.getTileValue()!=4)check(tile.getWorldBuilderSourceOverlay()==raw,"unsafe original reused");
   }
  }
  System.out.println("PASS imported resolver original count="+args[1]+" extended="+defs.size());
 }
}
'''
with tempfile.TemporaryDirectory(prefix='imported-floor-selection-') as tmp:
 out=Path(tmp);(out/'ImportedFloorProbe.java').write_text(java);jar=ROOT/'Client_Base/Open_RSC_Client.jar'
 subprocess.run(['javac','-cp',str(jar),'-d',tmp,str(out/'ImportedFloorProbe.java')],check=True)
 source=(ROOT/'current-platform/runtime/current-base-v1/public-definitions/TileDef.xml').read_bytes()
 for i,(payload,count) in enumerate([(source,25),(b'<TileDef-array><TileDef><colour>12345678</colour><unknown>0</unknown><objectType>0</objectType></TileDef></TileDef-array>',1)]):
  xml=out/f'{i}.xml';xml.write_bytes(floors.extend(payload))
  subprocess.run(['java','-cp',tmp+':'+str(jar),'com.openrsc.interfaces.misc.ImportedFloorProbe',str(xml),str(count)],check=True)
