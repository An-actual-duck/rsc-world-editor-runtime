#!/usr/bin/env python3
"""Map-only payload contracts and compiled package/material boundaries.

Optional selected-reference checks only compare source bytes; they never compile
or launch reference input. Execution uses this provider and synthetic fixtures.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / 'server/conf/world-builder/target-map-integration-v1.json'

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

stage = module('target_map_stage', ROOT / 'scripts/stage-target-map-integration.py')
fixture = module('target_map_fixture', ROOT / 'tests/myworld/test-native-blocked-void-npc-roam.py')

HARNESS = r'''
import java.nio.file.*;
import java.util.*;
import com.openrsc.server.io.*;
import com.openrsc.client.entityhandling.defs.TileDef;
public final class TargetMapHarness {
 public static void main(String[] args) throws Exception {
  if (args[0].equals("map")) {
   NativeLayeredWorldPackage map = NativeLayeredWorldPackage.load(Paths.get(args[1]));
   TargetOwnedMapPackageProfile.validate(NativeLayeredWorldPackageCatalog.of(Collections.singletonList(map)), "target-owned");
   NativeLayeredNpcPlacement npc = map.getPlacementSets().values().iterator().next().getNpcs().get(0);
   if (npc.getNpcId()!=Integer.parseInt(args[2])) throw new AssertionError("content identity changed");
   System.out.println("mapped:" + npc.getNpcId()); return;
  }
  List<TileDef> definitions = new ArrayList<>();
  TileDef custom = new TileDef(9123, 4, 1);
  definitions.add(custom);
  boolean rejected = false;
  try { orsc.WorldBuilderInstalledFloorDefinitions.appendTo(definitions); }
  catch (java.io.IOException failure) { rejected = true; }
  if (rejected != args[0].equals("reject")) throw new AssertionError("floor acceptance mismatch");
  if (definitions.get(0) != custom) throw new AssertionError("target definition replaced");
  if (definitions.size() != (rejected?1:2)) throw new AssertionError("partial floor mutation");
  if (!rejected && definitions.get(1).getWorldBuilderSourceOverlay()!=1) throw new AssertionError("floor ancestry lost");
 }
}
'''

class TargetMapIntegrationTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.contract=json.loads(CONTRACT.read_text())
  cls.temp=tempfile.TemporaryDirectory(prefix='target-map-compiled-')
  cls.classes=Path(cls.temp.name)
  harness=cls.classes/'TargetMapHarness.java';harness.write_text(HARNESS)
  cls.cp=os.pathsep.join(map(str,[cls.classes,ROOT/'server/core.jar',ROOT/'Client_Base/Open_RSC_Client.jar']))
  # Compile the exact provider-owned source payloads, not cached helper classes.
  sources=[]
  for row in cls.contract['adapters'][0]['sources']:
   sources.append(ROOT/('server' if row['scope']=='server' else 'Client_Base')/row['targetRelativePath'])
  subprocess.run(['javac','-proc:none','-implicit:none','-source','8','-target','8',
   '-cp',cls.cp,'-d',str(cls.classes),*map(str,sources),str(harness)],check=True,capture_output=True,text=True)
 @classmethod
 def tearDownClass(cls): cls.temp.cleanup()
 def run_java(self,*args,cwd=None):
  return subprocess.run(['java','-cp',self.cp,'TargetMapHarness',*map(str,args)],cwd=cwd or ROOT,capture_output=True,text=True,timeout=30)
 def test_payload_inventory_is_narrow_and_hash_bound(self):
  with tempfile.TemporaryDirectory(prefix='target-map-stage-') as tmp:
   root=Path(tmp);stage.stage(root)
   rows=self.contract['adapters'][0]['sources']
   self.assertGreater(len(rows),1)
   for row in rows:
    self.assertEqual(row['sha256'],hashlib.sha256((root/row['payloadRelativePath']).read_bytes()).hexdigest())
    self.assertNotIn(Path(row['targetRelativePath']).name,['EntityHandler.java','mudclient.java','Mob.java','World.java','ServerConfiguration.java'])
    self.assertNotIn('ProjectContent',row['targetRelativePath'])
    self.assertNotIn('AnimationRegistry',row['targetRelativePath'])
   staged={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()}
   self.assertEqual({row['payloadRelativePath'] for row in rows}|{str(stage.CONTRACT)},staged)
 def test_compiled_loader_keeps_arbitrary_ids_and_v4_v5_semantics(self):
  with tempfile.TemporaryDirectory(prefix='target-map-packages-') as tmp:
   for version in (4,5):
    for npc_id in (866,1924):
     root=Path(tmp)/f'{version}-{npc_id}';payload=fixture.package(root,version)
     payload['npcs'][0]['npcId']=npc_id
     payload['npcs'][0]['roamBounds']['maximum']['x']=47
     fixture.update(root,payload)
     result=self.run_java('map',root,npc_id)
     self.assertEqual(0,result.returncode,result.stderr)
     self.assertEqual(f'mapped:{npc_id}\n',result.stdout)
     payload['npcs'][0]['roamBounds']['maximum']['x']=50;fixture.update(root,payload)
     result=self.run_java('map',root,npc_id)
     self.assertEqual(version==5,result.returncode==0,result.stderr)
 def test_installed_floors_only_append_and_refuse_conflicts_atomically(self):
  with tempfile.TemporaryDirectory(prefix='target-map-floor-') as tmp:
   root=Path(tmp);directory=root/'world-builder-configs';directory.mkdir()
   for colour,mode in ((9123,'floor'),(9111,'reject')):
    payload=(f'<TileDef-array><TileDef><colour>{colour}</colour><unknown>4</unknown><objectType>1</objectType></TileDef>'
      f'<TileDef><colour>{colour}</colour><unknown>4</unknown><objectType>0</objectType><worldBuilderSourceOverlay>1</worldBuilderSourceOverlay></TileDef></TileDef-array>').encode()
    (directory/'TileDef.xml').write_bytes(payload)
    (directory/'installed-floors.json').write_text(json.dumps(dict(schemaVersion=1,manifestType='world-builder-installed-floor-definitions',tileDefinitionsRelativePath='world-builder-configs/TileDef.xml',tileDefinitionsSha256=hashlib.sha256(payload).hexdigest())))
    result=self.run_java(mode,cwd=root);self.assertEqual(0,result.returncode,result.stderr)
 def test_reference_source_applicability_without_execution(self):
  name=os.environ.get('WORLD_BUILDER_MAP_SOURCE_REFERENCE')
  if not name:self.skipTest('optional selected read-only map source not supplied')
  root=Path(name);adapter=self.contract['adapters'][0]
  for source in adapter['sources']:
   path=root/('server' if source['scope']=='server' else 'Client_Base')/source['targetRelativePath']
   if path.exists():
    self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(),source['acceptedBeforeSha256']+[source['sha256']])
  for transform in adapter['transforms']:
   path=root/('server' if transform['scope']=='server' else 'Client_Base')/transform['targetRelativePath'];original=path.read_text();text=original
   for edit in transform['edits']:
    self.assertEqual(edit['occurrences'],text.count(edit['before']),transform['targetRelativePath'])
    text=text.replace(edit['before'],edit['after'])
   # No edits touch target custom content or combat callback registration.
   for token in ('combatProjectileCollisionCounts','enemyProjectileFenceCollisionCounts','nativeTerrainStructuralCombatProjectileWall','nativeTerrainEnemyProjectileFenceWall','loadExternalNpcDirectionSheet'):
    self.assertEqual(original.count(token),text.count(token))
   self.assertEqual(original,path.read_text())
  for row in adapter['requirements']:
   path=root/('server' if row['scope']=='server' else 'Client_Base')/row['targetRelativePath'];text=path.read_text()
   for fragment in row['requiredFragments']:self.assertIn(fragment,text)
   if 'acceptedSourceSha256' in row:self.assertIn(hashlib.sha256(path.read_bytes()).hexdigest(),row['acceptedSourceSha256'])

if __name__=='__main__': unittest.main()
