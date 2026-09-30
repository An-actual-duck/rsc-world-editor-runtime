#!/usr/bin/env python3
"""Compile the shipped map edit recipes against a reconstructed provider host.

Only provider sources and synthetic callbacks are used. This is intentionally
not a build of the external reference or an assertion about its complete game.
The reconstruction reverses map features while keeping current unrelated code;
its pure-source hashes are fixture identities, not additional trusted targets.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
CONTRACT=ROOT/'server/conf/world-builder/target-map-integration-v1.json'

def write(path,text):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
def replace(text,before,after,count=1):
 if text.count(before)!=count:raise AssertionError(('fixture recipe mismatch',text.count(before),before[:120]))
 return text.replace(before,after)

def remove_method(text,signature):
 start=text.index(signature);brace=text.index('{',start);depth=1;end=brace+1
 while depth:
  if text[end]=='{':depth+=1
  elif text[end]=='}':depth-=1
  end+=1
 return text[:start]+text[end:]

CALLBACKS='''package synthetic;
public final class TargetContent {
 public static String npcVisual(int id) { return id == 1907 ? "target-dragon-sheet" : "target-salamander-sheet"; }
 public static String dialogue(int id) { return "custom-dialogue-" + id; }
 public static int itemEffect(int id) { return id * 17; }
 public static String objectInteraction(int id) { return "open-custom-object-" + id; }
}
'''
PLUGIN='''package synthetic;
public final class TargetPlugin {
 public static String interact() { return TargetContent.dialogue(1907); }
 public static int elevation(com.openrsc.server.model.world.region.TileValue tile) { return tile.elevation; }
}
'''
HARNESS='''import synthetic.*;
import com.openrsc.server.model.world.region.TileValue;
public final class TargetBehavior {
 public static void main(String[] args) throws Exception {
  if (!TargetContent.npcVisual(1907).equals("target-dragon-sheet") || !TargetContent.npcVisual(866).equals("target-salamander-sheet")) throw new AssertionError("visual callback");
  if (!TargetPlugin.interact().equals("custom-dialogue-1907")) throw new AssertionError("dialogue/plugin callback");
  if (TargetContent.itemEffect(812)!=13804 || !TargetContent.objectInteraction(920).equals("open-custom-object-920")) throw new AssertionError("item/object callback");
  boolean loaded = false;
  try {
   com.openrsc.server.io.NativeLayeredWorldPackage map = com.openrsc.server.io.NativeLayeredWorldPackage.load(java.nio.file.Paths.get(args[1]));
   loaded = true;
   if (map.getPlacementSets().values().iterator().next().getNpcs().get(0).getNpcId()!=1907) throw new AssertionError("placement identity");
   com.openrsc.server.io.NativeLayeredTerrainSector sector=map.getTerrainSectors().values().iterator().next();
   if (sector.getTile(0,0).getElevation()!=65535 || sector.copyWireBytes().length!=48*48*11) throw new AssertionError("wide map loader");
  } catch(java.io.IOException expectedOldLoader) { if(args[0].equals("after")) throw expectedOldLoader; }
  if (loaded != args[0].equals("after")) throw new AssertionError("loader was not upgraded");
  if (com.openrsc.server.io.NativeLayeredTerrainChunk.isWideEncoding("uniform-layered-sector-v2-u16") != args[0].equals("after")) throw new AssertionError("wire map API was not upgraded");
  TileValue tile = new TileValue();
  if (!tile.targetCustomCollisionBehavior().equals("custom-policy-retained")) throw new AssertionError("mixed class custom method");
  if (args[0].equals("after")) {
   try { TileValue.class.getField("elevation").setInt(tile,65535); } catch(Exception failure) { throw new AssertionError(failure); }
   if (TargetPlugin.elevation(tile)!=65535) throw new AssertionError("plugin stale field ABI");
  }
 }
}
'''

def reconstruct(root,adapter):
 for scope,prefix in [('server','server'),('client','Client_Base')]:
  source=ROOT/prefix/'src';destination=root/prefix/'src'
  shutil.copytree(source,destination)
 # Old fixture had a profile name and inventory field owned by its game. Keep
 # those identities rather than replacing them when the new profile is added.
 for path in (root/'server/src').rglob('*.java'):
  text=path.read_text().replace('WORLD_BUILDER_INSTALLED','SPOILED_MILK_EDITOR_INSTALLED').replace('LAYERED_NATIVE_TERRAIN_INVENTORY_SHA256','FIXTURE_LEGACY_INVENTORY_SHA256')
  path.write_text(text)
 profile=root/'server/src/com/openrsc/server/io/NativeLayeredWorldRuntimeProfile.java';text=profile.read_text()
 text=replace(text,'\tSPOILED_MILK_EDITOR_INSTALLED("world-builder-installed", true),\n\tADAPTIVE_WORLD_BUILDER("adaptive-world-builder", true);','\tADAPTIVE_WORLD_BUILDER("adaptive-world-builder", true),\n\tSPOILED_MILK_EDITOR_INSTALLED(\n\t\t"spoiled-milk-editor-installed", true);')
 text=replace(text,'\t\t\t|| this == SPOILED_MILK_EDITOR_INSTALLED\n\t\t\t|| this == ADAPTIVE_WORLD_BUILDER;','\t\t\t|| this == ADAPTIVE_WORLD_BUILDER\n\t\t\t|| this == SPOILED_MILK_EDITOR_INSTALLED;')
 text=replace(text,'\t\treturn this == SPOILED_MILK_EDITOR_INSTALLED\n\t\t\t|| this == ADAPTIVE_WORLD_BUILDER;','\t\treturn replacesLegacyBasePopulation;')
 profile.write_text(text)
 conf=root/'server/src/com/openrsc/server/ServerConfiguration.java';text=conf.read_text()
 text=replace(text,'\t\tWorldBuilderInstalledServerProfile.apply(this);','\t\tapplyInstalledWorldBuilderMap();')
 text=text[:-2]+'\n\tprivate void applyInstalledWorldBuilderMap() { /* Synthetic old activation hook. */ }\n}\n';conf.write_text(text)
 chunk=root/'server/src/com/openrsc/server/io/NativeLayeredTerrainChunk.java';text=chunk.read_text()
 text=text[:-2]+'\n\tpublic static boolean isWideEncoding(String encoding) {\n\t\treturn NativeLayeredWorldPackage.RAW_ENCODING_V2.equals(encoding);\n\t}\n}\n';chunk.write_text(text)
 tile=root/'server/src/com/openrsc/server/model/world/region/TileValue.java';text=remove_method(tile.read_text(),'\tpublic static TileValue blockedVoid()')
 text=text[:-2]+'\n\tpublic String targetCustomCollisionBehavior() { return "custom-policy-retained"; }\n}\n';tile.write_text(text)
 region=root/'server/src/com/openrsc/server/model/world/region/RegionManager.java';text=region.read_text()
 text=replace(text,'\t\tif (nativeLayeredWorldPackageCatalog != null\n\t\t\t&& nativeLayeredWorldRuntimeProfile.skipsLegacyTerrainArchive()) {\n\t\t\treturn TileValue.blockedVoid();\n\t\t}\n','')
 region.write_text(text)
 for transform in adapter['transforms']:
  path=root/('server' if transform['scope']=='server' else 'Client_Base')/transform['targetRelativePath'];text=path.read_text()
  for edit in reversed(transform['edits']):
   if text.count(edit['after'])==edit['occurrences']:
    text=text.replace(edit['after'],edit['before'])
   elif text.count(edit['before'])!=edit['occurrences']:
    raise AssertionError(('cannot reconstruct',transform['targetRelativePath'],edit['before'][:80]))
  path.write_text(text)
 # Older byte elevation APIs used a zero-valued byte for empty containers.
 path=root/'server/src/com/openrsc/server/model/world/region/LayeredPackedRegionBlankContainerPlan.java'
 path.write_text(replace(path.read_text(),'public int getInitialElevationValue()','public byte getInitialElevationValue()'))
 # Reconstruct the older in-game authoring assignment alongside its byte field.
 path=root/'server/src/com/openrsc/server/net/rsc/handlers/WorldEditorHandler.java'
 path.write_text(replace(path.read_text(),'runtime.elevation=s.elevation;','runtime.elevation=(byte)s.elevation;'))
 # Existing void callers were reversed above. The old parser still exposes its
 # map API to this host, but refuses v5 payloads until the reviewed replacement.
 path=root/'server/src/com/openrsc/server/io/NativeLayeredWorldPackage.java';text=path.read_text()
 text=replace(text,'boolean version5 = schemaVersion == 5','boolean version5 = false && schemaVersion == 5');path.write_text(text)
 write(root/'server/src/synthetic/TargetContent.java',CALLBACKS)
 write(root/'server/plugins/synthetic/TargetPlugin.java',PLUGIN)
 return root

def compile_sources(source,output,classpath):
 output.mkdir(parents=True,exist_ok=True)
 sources=sorted(source.rglob('*.java'))
 argfile=output.parent/(output.name+'-sources.txt')
 argfile.write_text('\n'.join('"'+str(p)+'"' for p in sources))
 result=subprocess.run(['javac','-proc:none','-implicit:none','-source','8','-target','8','-encoding','UTF-8','-sourcepath','',
  '-cp',os.pathsep.join(map(str,classpath)),'-d',str(output),'@'+str(argfile)],capture_output=True,text=True,timeout=180)
 if result.returncode:raise AssertionError(result.stderr[-18000:])

class TargetMapAdapterCompilationTest(unittest.TestCase):
 def test_all_shipped_source_edits_compile_and_preserve_custom_callbacks(self):
  adapter=json.loads(CONTRACT.read_text())['adapters'][0]
  with tempfile.TemporaryDirectory(prefix='target-map-adapted-host-') as tmp:
   root=Path(tmp);host=reconstruct(root/'host',adapter);before=root/'before';after=root/'after'
   library=ROOT/'server/core.jar';clientlib=ROOT/'Client_Base/Open_RSC_Client.jar'
   compile_sources(host/'server/src',before/'server',[library])
   compile_sources(host/'server/plugins',before/'plugins',[before/'server',library])
   specification=importlib.util.spec_from_file_location('map_fixture',ROOT/'tests/myworld/test-native-blocked-void-npc-roam.py')
   fixture=importlib.util.module_from_spec(specification);specification.loader.exec_module(fixture)
   package=root/'map';placements=fixture.package(package,5);placements['npcs'][0]['npcId']=1907;fixture.update(package,placements)
   terrain=dict(schemaVersion=2,encoding='uniform-layered-sector-v2-u16',size=48,
    tile=dict(elevation=65535,texture=0,overlay=0,roof=0,verticalWall=0,horizontalWall=0,diagonalWall=0))
   digest=fixture.write_json(package/'terrain.json',terrain);manifest=json.loads((package/'manifest.json').read_text())
   manifest['terrainSectors'][0].update(encoding=terrain['encoding'],path='terrain.json',sha256=digest)
   fixture.write_json(package/'manifest.json',manifest)
   write(root/'harness/TargetBehavior.java',HARNESS)
   compile_sources(root/'harness',root/'harness-classes',[before/'server',before/'plugins',library])
   def behavior(mode,classes):
    subprocess.run(['java','-cp',os.pathsep.join(map(str,[root/'harness-classes',classes/'server',classes/'plugins',library])),
     'TargetBehavior',mode,str(package)],check=True,capture_output=True,text=True,timeout=30)
   behavior('before',before)
   preserved={p.relative_to(host):p.read_bytes() for p in host.rglob('*.java')}
   changed=set()
   for source in adapter['sources']:
    relative=Path('server' if source['scope']=='server' else 'Client_Base')/source['targetRelativePath']
    target=host/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/relative).read_bytes());changed.add(relative)
   for transform in adapter['transforms']:
    relative=Path('server' if transform['scope']=='server' else 'Client_Base')/transform['targetRelativePath'];path=host/relative;text=path.read_text()
    for edit in transform['edits']:text=replace(text,edit['before'],edit['after'],edit['occurrences'])
    path.write_text(text);changed.add(relative)
   for relative,payload in preserved.items():
    if relative not in changed:self.assertEqual(payload,(host/relative).read_bytes(),str(relative))
   compile_sources(host/'server/src',after/'server',[library])
   compile_sources(host/'server/plugins',after/'plugins',[after/'server',library])
   # Compile every changed client owner against its original client/dependency
   # archive; no target startup or imported appearance provider is executed.
   selected=root/'client-selected'
   for relative in changed:
    if relative.parts[0]=='Client_Base':
     target=selected/Path(*relative.parts[2:]);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((host/relative).read_bytes())
   for compilation in adapter['compilation']:
    if compilation['scope']=='client':
     for relative in compilation.get('verificationSources',[]):
      source=host/'Client_Base'/relative;target=selected/Path(*Path(relative).parts[1:])
      target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(source.read_bytes())
   compile_sources(selected,after/'client',[clientlib,library])
   behavior('after',after)
   self.assertEqual((before/'server/synthetic/TargetContent.class').read_bytes(),(after/'server/synthetic/TargetContent.class').read_bytes())
   self.assertNotEqual((before/'plugins/synthetic/TargetPlugin.class').read_bytes(),(after/'plugins/synthetic/TargetPlugin.class').read_bytes())

if __name__=='__main__': unittest.main()
