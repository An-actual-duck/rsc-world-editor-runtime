#!/usr/bin/env python3
"""Positive, reference-checkout-independent integrity for public Base data."""

import hashlib
import base64
import gzip
import importlib.util
import io
import json
from pathlib import Path
import unittest
import tempfile
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT = ROOT / "current-platform/runtime/current-base-v1/public-definitions"


def records(name):
    path = SNAPSHOT / name
    if name.endswith('.json'):
        value = json.loads(path.read_bytes())
        assert len(value) == 1
        return next(iter(value.values()))
    return [{field.tag: (field.text or '').strip() for field in row}
            for row in ET.fromstring(path.read_bytes())]


class PublicDefinitionSnapshotTest(unittest.TestCase):
    def test_closed_profile_provenance_binding_and_forgery_refusal(self):
        spec = importlib.util.spec_from_file_location('public_policy_verify', ROOT / 'scripts/verify-current-base.py')
        verify = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(verify)
        profile = verify.validate_profile(SNAPSHOT.parent / 'profile.json')
        policy = profile['definitionPolicy']
        for name, expected_hash in policy['provenanceSha256'].items():
            self.assertEqual(hashlib.sha256((SNAPSHOT / name).read_bytes()).hexdigest(), expected_hash)
        with tempfile.TemporaryDirectory(prefix='public-policy-forgery-') as tmp:
            forged = Path(tmp) / 'profile.json'
            for field, value in [('sourceCommit', '0' * 40), ('registryCounts', {'items': 1290}),
                                 ('provenanceSha256', {}), ('unknown', True)]:
                altered = json.loads(json.dumps(profile))
                altered['definitionPolicy'][field] = value
                forged.write_text(json.dumps(altered))
                with self.assertRaisesRegex(verify.VerificationError, 'definition policy'):
                    verify.validate_profile(forged)
        for role in ('server', 'client'):
            manifest = json.loads((SNAPSHOT.parent / (role + '-content.json')).read_bytes())
            verify.validate_public_provenance_selection(manifest, role)
            manifest['sourceFiles'] = [row for row in manifest['sourceFiles']
                                       if not row['bundlePath'].endswith('/effective-policy.json')]
            with self.assertRaisesRegex(verify.VerificationError, 'provenance selection'):
                verify.validate_public_provenance_selection(manifest, role)

    def test_client_content_payload_tampering_and_duplicate_paths_refused(self):
        def module(name, filename):
            spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / filename)
            result = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(result)
            return result
        build = module('public_content_build', 'build-current-base.py')
        verify = module('public_content_verify', 'verify-current-base.py')
        manifest_path = SNAPSHOT.parent / 'client-content.json'
        with tempfile.TemporaryDirectory(prefix='public-content-payload-') as tmp:
            root = Path(tmp)
            archive = root / 'client.zip'
            build.write_client_content_archive(archive)
            verify.validate_client_content(manifest_path, archive)
            with zipfile.ZipFile(archive) as source:
                payloads = {name: source.read(name) for name in source.namelist()}
            audio = next(name for name in payloads if name.startswith('Cache/audio/'))
            for name in ['Cache/video/CurrentBase_Public_Sprites.osar',
                         'Cache/current-base-definitions/ItemDefs.json', audio]:
                changed = root / 'changed.zip'
                with zipfile.ZipFile(changed, 'w', compression=zipfile.ZIP_DEFLATED) as output:
                    for path, payload in payloads.items():
                        output.writestr(path, payload + b'X' if path == name else payload)
                with self.assertRaisesRegex(verify.VerificationError, 'payload differs'):
                    verify.validate_client_content(manifest_path, changed)
            manifest = json.loads(manifest_path.read_bytes())
            manifest['sourceFiles'].append(dict(manifest['sourceFiles'][0]))
            forged = root / 'manifest.json'
            forged.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(verify.VerificationError, 'duplicate'):
                verify.validate_client_content(forged, archive)
            manifest['sourceFiles'].pop()
            invalid = root / 'invalid.base64'
            invalid.write_bytes(b'not%%%base64')
            next(row for row in manifest['sourceFiles'] if row['transform'] == 'base64')['sourcePath'] = str(invalid)
            forged.write_text(json.dumps(manifest))
            with self.assertRaisesRegex(verify.VerificationError, 'invalid.*base64'):
                verify.validate_client_content(forged, archive)

    def test_public_gameplay_hook_provenance_and_no_cap_filtering(self):
        document = json.loads((SNAPSHOT / 'gameplay-provenance.json').read_bytes())
        self.assertEqual(document['sourceCommit'], 'c0102e60774ab9c9076aabae49f6f97fb6fc4b00')
        self.assertEqual(len(document['files']), 23)
        manifest = json.loads((SNAPSHOT.parent / 'server-content.json').read_bytes())
        sources = {row['bundlePath']: row for row in manifest['sourceFiles']}
        for row in document['files']:
            payload = (SNAPSHOT / row['path']).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(), row['sha256'])
            self.assertEqual(len(payload), row['size'])
            original = payload if row['sourceFinalNewline'] else payload[:-1]
            if row['sourceLineEndings'] == 'crlf':
                original = original.replace(b'\n', b'\r\n')
            self.assertEqual(hashlib.sha256(original).hexdigest(), row['sourceSha256'])
            self.assertEqual(len(original), row['sourceSize'])
            self.assertEqual(len(ET.fromstring(payload)), row['recordCount'])
            selected = sources['conf/server/defs/' + row['path']]
            self.assertEqual(selected['transform'], 'copy')
            self.assertEqual(selected['sourcePath'], 'current-platform/runtime/current-base-v1/public-definitions/' + row['path'])
        generated = {row['bundlePath']: row['content'] for row in manifest['generatedFiles']}
        for filename in document['disabledHookMaps']:
            self.assertEqual(generated['conf/server/defs/extras/' + filename], '<map/>')

    def test_closed_visual_derivation_literals_reject_code(self):
        spec = importlib.util.spec_from_file_location('public_visuals',
            ROOT / 'scripts/derive-current-base-public-item-visuals.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.Literals('Config.S_WANT_CUSTOM_SPRITES ? 9 : -1, "items:7", 0xff').arguments(),
                         [-1, 'items:7', 255])
        for bad in ['Runtime.exec("x")', 'Config.UNREVIEWED ? 1 : 2', 'foo()', '1; 2']:
            with self.assertRaises(ValueError):
                module.Literals(bad).arguments()
        with self.assertRaises(ValueError):
            module.derive(b'not-the-reviewed-source')

    def test_exact_public_visual_inputs(self):
        provenance = json.loads((SNAPSHOT / 'visual-provenance.json').read_bytes())
        visual = provenance['itemVisuals']
        payload = (SNAPSHOT / visual['path']).read_bytes()
        self.assertEqual(len(payload), visual['size'])
        self.assertEqual(hashlib.sha256(payload).hexdigest(), visual['sha256'])
        document = json.loads(payload)
        self.assertEqual(set(document), {'schemaVersion', 'manifestType', 'sourceSha256', 'flags', 'items'})
        self.assertEqual(document['sourceSha256'], visual['sourceSha256'])
        self.assertEqual(list(row['id'] for row in document['items']), list(range(1593)))
        self.assertTrue(all(value is False for value in document['flags'].values()))
        for row in document['items']:
            self.assertEqual(set(row), {'id', 'authenticSpriteId', 'spriteLocation', 'pictureMask', 'blueMask'})
            self.assertTrue(row['spriteLocation'].startswith('items:'))
        stock = provenance['stockSprites']
        archive = base64.b64decode(b''.join((SNAPSHOT / stock['path']).read_bytes().split()), validate=True)
        self.assertEqual(len(archive), stock['sourceSize'])
        self.assertEqual(hashlib.sha256(archive).hexdigest(), stock['sourceSha256'])
        with gzip.GzipFile(fileobj=io.BytesIO(archive)) as stream:
            unpacked = stream.read(16000001)
            self.assertLessEqual(len(unpacked), 16000000)
            self.assertEqual(stream.read(1), b'')
        authentic = provenance['authenticSprites']
        self.assertEqual(hashlib.sha256((ROOT / authentic['sourcePath']).read_bytes()).hexdigest(),
                         authentic['sourceSha256'])

    def test_closed_provenance_and_reconstruct_original_bytes(self):
        manifest = json.loads((SNAPSHOT / 'provenance.json').read_bytes())
        self.assertEqual(set(manifest), {'schemaVersion', 'manifestType', 'sourceCommit',
                         'sourceTree', 'encoding', 'normalization', 'files'})
        self.assertEqual(manifest['schemaVersion'], 1)
        self.assertEqual(manifest['manifestType'], 'current-base-public-definition-snapshot')
        self.assertEqual(manifest['sourceCommit'], 'c0102e60774ab9c9076aabae49f6f97fb6fc4b00')
        self.assertEqual(manifest['sourceTree'], '6db5536d795abf34f303bb03b20c43b8cfb9e3fe')
        self.assertEqual(manifest['encoding'], 'utf-8')
        self.assertEqual(manifest['normalization'], 'xml-lf-with-final-newline-json-byte-identical')
        self.assertEqual({row['path'] for row in manifest['files']}, {
            'DoorDef.xml', 'GameObjectDef.xml', 'ItemDefs.json', 'ItemDefsCustom.json',
            'NpcDefs.json', 'NpcDefsCustom.json', 'TileDef.xml'})
        self.assertEqual(len(manifest['files']), 7)
        for row in manifest['files']:
            self.assertEqual(set(row), {'path', 'sourcePath', 'sourceSha256', 'sourceSize',
                             'sourceLineEndings', 'sha256', 'size', 'recordCount'})
            self.assertEqual(row['sourcePath'], 'server/conf/server/defs/' + row['path'])
            payload = (SNAPSHOT / row['path']).read_bytes()
            self.assertEqual(len(payload), row['size'])
            self.assertEqual(hashlib.sha256(payload).hexdigest(), row['sha256'])
            payload.decode('utf-8', errors='strict')
            original = payload
            if row['sourceLineEndings'] != 'unchanged':
                self.assertTrue(payload.endswith(b'\n'))
                self.assertNotIn(b'\r', payload)
                original = payload[:-1]
                if row['sourceLineEndings'] == 'crlf-no-final-newline':
                    original = original.replace(b'\n', b'\r\n')
                else:
                    self.assertEqual(row['sourceLineEndings'], 'lf-no-final-newline')
            self.assertEqual(len(original), row['sourceSize'])
            self.assertEqual(hashlib.sha256(original).hexdigest(), row['sourceSha256'])
            self.assertEqual(len(records(row['path'])), row['recordCount'])

    def test_complete_item_ids_and_stock_appended_state_ids(self):
        base, custom = records('ItemDefs.json'), records('ItemDefsCustom.json')
        self.assertEqual([r['id'] for r in base], list(range(1290)))
        self.assertEqual([r['id'] for r in custom], list(range(1290, 1593)))
        rows = base + custom
        self.assertEqual(rows[2]['name'], 'Iron Kite Shield')
        self.assertEqual(rows[101]['name'], 'Staff of Air')
        self.assertEqual(rows[611]['name'], 'Unpowered orb')
        self.assertEqual(rows[1592]['name'], 'Boomstick')

    def test_complete_npc_order_including_stock_appended_records(self):
        base, custom = records('NpcDefs.json'), records('NpcDefsCustom.json')
        self.assertEqual(len(base), 794)
        self.assertEqual(len(custom), 42)
        self.assertEqual((base + custom)[825]['name'], 'Ana (not in a barrel)')

    def test_positive_collision_and_interaction_definitions(self):
        rows = records('GameObjectDef.xml')
        self.assertEqual(len(rows), 1296)
        self.assertEqual((rows[2]['width'], rows[2]['height']), ('2', '2'))
        self.assertEqual(rows[21]['type'], '0')
        self.assertEqual((rows[199]['name'], rows[199]['type'], rows[199]['command1']),
                         ('Ladder', '1', 'Climb-Down'))
        self.assertEqual(len(records('DoorDef.xml')), 214)
        self.assertEqual(len(records('TileDef.xml')), 25)


if __name__ == '__main__':
    unittest.main()
