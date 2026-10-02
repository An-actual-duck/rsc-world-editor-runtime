#!/usr/bin/env python3
"""Reviewed animation export parity with maintained Java registry and allocator."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / 'current-platform/runtime/current-base-v1/public-definitions'
spec = importlib.util.spec_from_file_location('animation_export', ROOT / 'scripts/derive-current-base-public-animation-visuals.py')
exporter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(exporter)


class AnimationVisualTest(unittest.TestCase):
    def test_reproducible_reviewed_lookup_and_provenance(self):
        data = exporter.derive((ROOT / exporter.SOURCE_PATH).read_bytes(), (ROOT / exporter.ALLOCATOR_PATH).read_bytes())
        encoded = (json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
        self.assertEqual(encoded, (PUBLIC / 'animation-visuals.json').read_bytes())
        proof = json.loads((PUBLIC / 'animation-visual-provenance.json').read_bytes())
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), proof['sha256'])
        self.assertEqual(len(encoded), proof['size'])
        self.assertEqual(229, proof['recordCount'])
        for key in ('sourceSha256', 'allocatorSourceSha256', 'profileId', 'flags'):
            self.assertEqual(data[key], proof[key])
        self.assertEqual(list(range(229)), [row['animationId'] for row in data['animations']])
        self.assertEqual('scythe', data['animations'][-1]['name'])
        config = (ROOT / proof['profileConfigurationPath']).read_bytes()
        self.assertEqual(hashlib.sha256(config).hexdigest(), proof['profileConfigurationSha256'])
        self.assertIn('custom_sprites: false', config.decode())
        self.assertIn('ALLOW_BEARDED_LADIES = tryReadBool("allow_bearded_ladies").orElse(false);',
                      (ROOT / 'server/src/com/openrsc/server/ServerConfiguration.java').read_text())

    def test_unreviewed_source_and_allocator_refuse(self):
        source = (ROOT / exporter.SOURCE_PATH).read_bytes()
        allocator = (ROOT / exporter.ALLOCATOR_PATH).read_bytes()
        for changed_source, changed_allocator in ((source + b'\n', allocator), (source, allocator.replace(b'animationNumber += 27;', b'animationNumber += 26;'))):
            with self.assertRaisesRegex(ValueError, 'exact reviewed'):
                exporter.derive(changed_source, changed_allocator)

    def test_allocator_case_insensitive_reuse_and_reserved_gap(self):
        rows = [{'name': 'sprite' + str(i)} for i in range(75)]
        rows.insert(1, {'name': 'SPRITE0'})
        result = exporter.allocate(rows)
        self.assertEqual([0, 0, 27], [row['authenticBaseSpriteId'] for row in result[:3]])
        self.assertEqual(1971, result[-2]['authenticBaseSpriteId'])
        self.assertEqual(3300, result[-1]['authenticBaseSpriteId'])

    def test_actual_maintained_java_registry_and_allocator_match_every_row(self):
        self.assertIsNotNone(shutil.which('javac'), 'Java compiler required for renderer parity')
        source = (ROOT / exporter.SOURCE_PATH).read_text()
        allocator = (ROOT / exporter.ALLOCATOR_PATH).read_text()
        method = allocator[allocator.index('private void loadEntitiesAuthentic() {'):allocator.index('private void loadGameConfig(boolean var1) {')]
        prefix = exporter.registry_prefix(source) + '\n}\n'
        harness = '''import java.util.*;
import com.openrsc.client.entityhandling.defs.extras.AnimationDef;
public class AnimationProbe {
static ArrayList<AnimationDef> animations = new ArrayList<>();
static Map<Object,Object> PROJECT_NPC_ANIMATIONS = new HashMap<>();
static class Config { static boolean S_ALLOW_BEARDED_LADIES=false; }
static class ProjectNpcAnimationRegistry { static class EntryDef { boolean hasRgbFrames(){return false;} } }
static class EntityHandler {
 static int animationCount(){return animations.size();}
 static AnimationDef getAnimationDef(int id){return animations.get(id);}
 static ProjectNpcAnimationRegistry.EntryDef getProjectNpcAnimation(AnimationDef animation){return null;}
}
static class Port { void showLoadingProgress(int number,String text){} }
Port clientPort = new Port();
void loadSprite(int number,String name,int count){}
''' + prefix + method + '''
public static void main(String[] args) {
 loadAnimationDefinitions(); new AnimationProbe().loadEntitiesAuthentic();
 for(int i=0;i<animations.size();i++) { AnimationDef a=animations.get(i);
  System.out.println(i+"\\t"+a.getName()+"\\t"+a.category+"\\t"+a.getCharColour()+"\\t"+a.getBlueMask()+"\\t"+a.getGenderModel()+"\\t"+a.hasA()+"\\t"+a.hasF()+"\\t"+a.getNumber());
 }
 animations.clear();
 for(int i=0;i<75;i++) animations.add(new AnimationDef("probe"+i,"npc",0,0,false,false,0));
 animations.add(1,new AnimationDef("PROBE0","npc",0,0,false,false,0));
 new AnimationProbe().loadEntitiesAuthentic();
 System.out.println("allocator:"+animations.get(1).getNumber()+":"+animations.get(74).getNumber()+":"+animations.get(75).getNumber());
}
}
'''
        with tempfile.TemporaryDirectory(prefix='animation-visual-parity-') as temporary:
            root = Path(temporary)
            (root / 'AnimationProbe.java').write_text(harness)
            animation = ROOT / 'Client_Base/src/com/openrsc/client/entityhandling/defs/extras/AnimationDef.java'
            subprocess.run(['javac', '-d', str(root), str(animation), str(root / 'AnimationProbe.java')], check=True, capture_output=True)
            result = subprocess.run(['java', '-cp', str(root), 'AnimationProbe'], check=True, capture_output=True, text=True)
        rows = json.loads((PUBLIC / 'animation-visuals.json').read_bytes())['animations']
        actual = []
        self.assertEqual('allocator:0:1971:3300', result.stdout.splitlines()[-1])
        for line in result.stdout.splitlines()[:-1]:
            identity, name, category, colour, blue, gender, combat, special, number = line.split('\t')
            actual.append({'animationId': int(identity), 'name': name, 'category': category,
                           'charColour': int(colour), 'blueMask': int(blue), 'genderModel': int(gender),
                           'hasCombatFrames': combat == 'true', 'hasSpecialCombatFrames': special == 'true',
                           'requiredFrameCount': 27 if special == 'true' else 18 if combat == 'true' else 15,
                           'authenticBaseSpriteId': int(number)})
        self.assertEqual(rows, actual)
        self.assertTrue(any(row['requiredFrameCount'] == 15 for row in actual))
        self.assertTrue(any(row['requiredFrameCount'] == 27 for row in actual))


if __name__ == '__main__':
    unittest.main(verbosity=2)
