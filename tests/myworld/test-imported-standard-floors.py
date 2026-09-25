#!/usr/bin/env python3
"""Append-only imported floor extension, including partial catalogs and refusals."""
from pathlib import Path
import importlib.util
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('floors', ROOT / 'scripts/standard-floors.py')
floors = importlib.util.module_from_spec(spec)
spec.loader.exec_module(floors)


def row(colour=7, unknown=0, blocking=0, extra=''):
    return f'<TileDef><colour>{colour}</colour><unknown>{unknown}</unknown><objectType>{blocking}</objectType>{extra}</TileDef>'


def catalog(rows):
    return ('<?xml version="1.0"?>\n<TileDef-array>\n' + '\n'.join(rows) + '\n</TileDef-array>').encode()


class ImportedFloors(unittest.TestCase):
    def test_custom_source_preserved_minimal_and_idempotent(self):
        source = catalog([row(91, 4, 1), row(-913, 2, 0), row(12345678, 0, 0)])
        extended = floors.extend(source)
        rows = list(ET.fromstring(extended))
        self.assertEqual(10, len(rows))  # original3 + ordinary1 + projectile2 + invisible2 + base2
        self.assertTrue(extended.startswith(source.split(b'</TileDef-array>')[0]))
        self.assertEqual(extended, floors.extend(extended))
        partners = [(int(x.findtext('worldBuilderSourceOverlay')), int(x.findtext('objectType')))
                    for x in rows if x.find('worldBuilderSourceOverlay') is not None]
        self.assertEqual([(1, 0), (2, 0), (2, 1), (3, 0), (3, 1)], partners)
        self.assertEqual('91', rows[3].findtext('colour'))

    def test_partial_catalog_reuses_pairs_and_preserves_existing_ids(self):
        source = catalog([row(55), row(66), row(55, extra='<worldBuilderSourceOverlay>1</worldBuilderSourceOverlay>'),
                          row(0, extra='<worldBuilderMaterial>base-color-v1</worldBuilderMaterial>')])
        extended = floors.extend(source)
        rows = list(ET.fromstring(extended))
        self.assertEqual(8, len(rows))
        self.assertEqual(source.split(b'</TileDef-array>')[0], extended[:len(source.split(b'</TileDef-array>')[0])])
        self.assertEqual('1', rows[4].findtext('worldBuilderSourceOverlay'))
        self.assertEqual('1', rows[4].findtext('objectType'))
        self.assertEqual(extended, floors.extend(extended))

    def test_omitted_legacy_fields_default_to_zero(self):
        source = catalog(['<TileDef/>'])
        rows = ET.fromstring(floors.extend(source))
        self.assertEqual(4, len(rows))
        self.assertEqual('0', rows[1].findtext('colour'))
        self.assertEqual('0', rows[1].findtext('unknown'))
        self.assertEqual('1', rows[1].findtext('objectType'))

    def test_stable_base_transform_and_completed_catalog(self):
        source = (ROOT / 'current-platform/runtime/current-base-v1/public-definitions/TileDef.xml').read_bytes()
        stable = floors.transform(source)
        self.assertEqual(77, len(ET.fromstring(stable)))
        self.assertEqual(stable, floors.extend(stable))
        self.assertLess(len(ET.fromstring(floors.extend(source))), 77)

    def test_identical_appearance_does_not_collapse_distinct_source_identity(self):
        extended = ET.fromstring(floors.extend(catalog([row(), row(), row()])))
        self.assertEqual([1, 2, 2, 3], [int(x.findtext('worldBuilderSourceOverlay')) for x in extended if x.find('worldBuilderSourceOverlay') is not None])

    def test_capacity_preflight_and_malformed_markers(self):
        with self.assertRaisesRegex(ValueError, 'additional slots'):
            floors.extend(catalog([row()] * 249))
        source = row()
        invalid = [row(extra='<worldBuilderMaterial/>'), row(extra='<worldBuilderMaterial>unknown</worldBuilderMaterial>'),
                   row(extra='<worldBuilderSourceOverlay>0</worldBuilderSourceOverlay>'),
                   row(extra='<worldBuilderSourceOverlay>2</worldBuilderSourceOverlay>'),
                   row(8, extra='<worldBuilderSourceOverlay>1</worldBuilderSourceOverlay>'),
                   row(extra='<worldBuilderSourceOverlay>1</worldBuilderSourceOverlay>' * 2),
                   row(extra='<nested><worldBuilderSourceOverlay>1</worldBuilderSourceOverlay></nested>'),
                   row(extra='<colour>7</colour>'), row(blocking=2), row(colour=2147483648)]
        for bad in invalid:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                floors.extend(catalog([source, bad]))
        with self.assertRaises(ValueError):
            floors.extend(catalog([source, row(extra='<worldBuilderSourceOverlay>1</worldBuilderSourceOverlay>'),
                                  row(extra='<worldBuilderSourceOverlay>2</worldBuilderSourceOverlay>')]))


if __name__ == '__main__':
    unittest.main()
