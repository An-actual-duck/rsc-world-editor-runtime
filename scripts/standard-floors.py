#!/usr/bin/env python3
"""Append current floor-authoring definitions without rewriting imported rows."""
from copy import deepcopy
import xml.etree.ElementTree as ET

TRANSFORM = 'standard-floors-v1'

def transform(payload: bytes) -> bytes:
    root = ET.fromstring(payload)
    if root.tag != 'TileDef-array' or any(row.tag != 'TileDef' for row in root):
        raise ValueError('Expected TileDef-array')
    originals = list(root)
    if any(row.find('worldBuilderMaterial') is not None or row.find('worldBuilderSourceOverlay') is not None for row in originals):
        raise ValueError('Standard floors must be applied once to an unmarked definition source')
    additions = []
    for raw, row in enumerate(originals, 1):
        values = {name: int(row.findtext(name)) for name in ('colour', 'unknown', 'objectType')}
        if values['objectType'] not in (0, 1):
            raise ValueError('Standard floor sources require canonical blocking flags')
        for blocking in (0, 1):
            partner = deepcopy(row)
            partner.find('objectType').text = str(blocking)
            ET.SubElement(partner, 'worldBuilderSourceOverlay').text = str(raw)
            additions.append(partner)
    for blocking in (0, 1):
        row = ET.Element('TileDef')
        for name, value in (('colour', '0'), ('unknown', '0'), ('objectType', str(blocking)), ('worldBuilderMaterial', 'base-color-v1')):
            ET.SubElement(row, name).text = value
        additions.append(row)
    if len(originals) + len(additions) > 249:
        raise ValueError('Standard floor definitions exceed available non-reserved overlay slots')
    # Preserve every original source byte, including provenance-sensitive field order.
    closing = b'</TileDef-array>'
    if payload.count(closing) != 1:
        raise ValueError('Expected one TileDef-array closing tag')
    appendix = b''.join(ET.tostring(row, encoding='utf-8') + b'\n' for row in additions)
    return payload.replace(closing, appendix + closing)
