#!/usr/bin/env python3
"""Execute semantic selection, actual renderer inputs, and terrain byte round trips."""
from pathlib import Path
import importlib.util
import subprocess
import tempfile
import xml.etree.ElementTree as ET
ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('standard_floors', ROOT/'scripts/standard-floors.py')
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
original = (ROOT/'current-platform/runtime/current-base-v1/public-definitions/TileDef.xml').read_bytes()
standard = module.transform(original)
old = list(ET.fromstring(original)); new = list(ET.fromstring(standard))
assert len(new) == len(old)*3+2
assert [ET.tostring(x) for x in new[:len(old)]] == [ET.tostring(x) for x in old]
assert module.transform(original) == standard
try: module.transform(standard)
except ValueError: pass
else: raise AssertionError('Repeated standard transform accepted')
java = r'''
package com.openrsc.interfaces.misc;
import java.lang.reflect.*;
import java.nio.file.*;
import java.util.*;
import com.openrsc.client.entityhandling.*;
import com.openrsc.client.entityhandling.defs.TileDef;
import com.openrsc.client.model.*;
import orsc.graphics.three.*;
import orsc.util.GenUtil;
public class FriendlyFloorProbe {
 static void check(boolean yes,String message){if(!yes)throw new AssertionError(message);}
 static Object field(Object value,String name)throws Exception{Field f=value.getClass().getDeclaredField(name);f.setAccessible(true);return f.get(value);}
 static void set(Object value,String name,Object next)throws Exception{Field f=value.getClass().getDeclaredField(name);f.setAccessible(true);f.set(value,next);}
 public static void main(String[] args)throws Exception{
  Method load=EntityHandler.class.getDeclaredMethod("loadProjectTiles",Path.class);load.setAccessible(true);load.invoke(null,Paths.get(args[0]));
  final int count=EntityHandler.tileCount();
  WorldEditorFloorSelection.Definitions defs=new WorldEditorFloorSelection.Definitions(){public int size(){return count;}public TileDef get(int id){return EntityHandler.getTileDef(id);}public boolean allowed(int id){return true;}};
  for(int level:new int[]{-3,-1,0,1,2,5})for(int color=0;color<256;color++)for(boolean walk:new boolean[]{false,true}){
   int raw=WorldEditorFloorSelection.resolve(defs,0,walk,level);check(raw>0,"base unavailable");TileDef d=defs.get(raw-1);check(d.usesExplicitBaseColor()&&d.getObjectType()==(walk?0:1),"base semantics");
   Sector sector=new Sector();sector.getTile(0).groundTexture=(byte)color;sector.getTile(0).groundOverlay=(byte)raw;
   Sector round=Sector.unpack(sector.pack());check((round.getTile(0).groundTexture&255)==color&&(round.getTile(0).groundOverlay&255)==raw,"terrain roundtrip");
  }
  for(int raw=1;raw<=25;raw++)for(boolean walk:new boolean[]{false,true}){int resolved=WorldEditorFloorSelection.resolve(defs,raw,walk,2);check(resolved>25,"legacy ID used for standard selection");check(defs.get(resolved-1).getWorldBuilderSourceOverlay()==raw,"appearance changed");check(defs.get(resolved-1).getObjectType()==(walk?0:1),"walkability changed");}
  WorldEditorFloorSelection.Definitions legacy=new WorldEditorFloorSelection.Definitions(){public int size(){return 25;}public TileDef get(int id){return defs.get(id);}public boolean allowed(int id){return true;}};
  check(WorldEditorFloorSelection.resolve(legacy,0,true,1)==-1,"upper invisible substituted for color");check(WorldEditorFloorSelection.resolve(legacy,0,true,0)==0,"legacy ground disabled");check(WorldEditorFloorSelection.resolve(legacy,3,true,1)==3,"legacy appearance disabled");check(WorldEditorFloorSelection.resolve(legacy,3,false,1)==-1,"missing legacy partner invented");
  Field unsafeField=sun.misc.Unsafe.class.getDeclaredField("theUnsafe");unsafeField.setAccessible(true);sun.misc.Unsafe unsafe=(sun.misc.Unsafe)unsafeField.get(null);World world=(World)unsafe.allocateInstance(World.class);
  int[] palette=new int[256];for(int i=0;i<256;i++){int rgb=WorldEditorFloorSelection.paletteRgb(i);palette[i]=GenUtil.colorToResource(rgb>>16,(rgb>>8)&255,rgb&255);}set(world,"colorToResource",palette);
  Field sectorCount=World.class.getDeclaredField("ACTIVE_SECTION_COUNT");sectorCount.setAccessible(true);Sector[] sectors=new Sector[sectorCount.getInt(null)];for(int i=0;i<sectors.length;i++)sectors[i]=new Sector();
  Class<?> input=Class.forName("orsc.graphics.three.World$TerrainModelInputSource");Constructor<?> ctor=input.getDeclaredConstructor(Sector[].class);ctor.setAccessible(true);Object source=ctor.newInstance((Object)sectors);
  Method overlays=World.class.getDeclaredMethod("collectTerrainOverlayFaceInputs",int.class,input);overlays.setAccessible(true);
  Method collect=World.class.getDeclaredMethod("collectTerrainTileFaceInputs",int.class,input);collect.setAccessible(true);
  for(int level:new int[]{-2,0,1,2,5})for(int raw:new int[]{0,8,11,12,WorldEditorFloorSelection.resolve(defs,0,true,level),WorldEditorFloorSelection.resolve(defs,0,false,level),WorldEditorFloorSelection.resolve(defs,8,true,level),WorldEditorFloorSelection.resolve(defs,11,true,level),WorldEditorFloorSelection.resolve(defs,12,true,level)}){
   for(Sector sector:sectors)for(int i=0;i<2304;i++){sector.getTile(i).groundTexture=17;sector.getTile(i).groundOverlay=(byte)raw;}
   Object[] faces=(Object[])collect.invoke(world,level,source);Object face=null;for(Object candidate:faces)if((Integer)field(candidate,"x")==10&&(Integer)field(candidate,"z")==10){face=candidate;break;}check(face!=null,"missing interior tile");int resource=(Integer)field(face,"colorResource");
   if(raw==0)check(resource==(level==1||level==2?12345678:palette[17]),"legacy color changed");
   else if(defs.get(raw-1).usesExplicitBaseColor()){check(resource==palette[17],"explicit color invisible upstairs");check((Boolean)field(face,"collisionFullBlock")== (defs.get(raw-1).getObjectType()!=0),"render collision mismatch");}
   else if(defs.get(raw-1).getWorldBuilderSourceOverlay()==8){check(resource==12345678,"invisible not transparent");check((Boolean)field(face,"pickableInvisibleOverlay"),"invisible cannot be picked");}
   else if(defs.get(raw-1).getWorldBuilderSourceOverlay()==12){check(resource==31,"alternate water visual lost");Object[] bridges=(Object[])overlays.invoke(world,level,source);check(bridges.length>0&&(Integer)field(bridges[0],"texture")==3,"bridge surface material lost");}
   else if(defs.get(raw-1).getWorldBuilderSourceOverlay()==11)check((Boolean)field(face,"lavaGlowEmitter"),"lava glow lost");
  }
  Field tilesField=EntityHandler.class.getDeclaredField("tiles");tilesField.setAccessible(true);java.util.List<TileDef> loaded=(java.util.List<TileDef>)tilesField.get(null);int customOriginal=loaded.size()+1;loaded.add(new TileDef(12345678,4,0));loaded.add(new TileDef(12345678,4,1,"",customOriginal));TileDef.validateWorldBuilderDefinitions(loaded);
  for(Sector sector:sectors)for(int i=0;i<2304;i++)sector.getTile(i).groundOverlay=(byte)loaded.size();
  Object[] customFaces=(Object[])collect.invoke(world,0,source);Object customFace=null;for(Object candidate:customFaces)if((Integer)field(candidate,"x")==10&&(Integer)field(candidate,"z")==10)customFace=candidate;
  check((Integer)field(customFace,"colorResource")==1,"transparent bridge surface erased underlying water");check(!(Boolean)field(customFace,"pickableInvisibleOverlay"),"water bridge mislabeled invisible");
  System.out.println("PASS: all palette colors, levels, traversal variants, legacy fallback, renderer inputs and save/reopen bytes");
 }
}
'''
with tempfile.TemporaryDirectory(prefix='friendly-floor-') as tmp:
    out=Path(tmp);(out/'TileDef.xml').write_bytes(standard);(out/'FriendlyFloorProbe.java').write_text(java)
    jar=ROOT/'Client_Base/Open_RSC_Client.jar'
    subprocess.run(['javac','-cp',str(jar),'-d',str(out),str(out/'FriendlyFloorProbe.java')],check=True)
    subprocess.run(['java','-cp',str(out)+':'+str(jar),'com.openrsc.interfaces.misc.FriendlyFloorProbe',str(out/'TileDef.xml')],check=True,cwd=ROOT)
