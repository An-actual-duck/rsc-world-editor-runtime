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
