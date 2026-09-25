#!/usr/bin/env python3
"""Append current floor-authoring definitions without rewriting imported rows."""
from copy import deepcopy
import xml.etree.ElementTree as ET
import re

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


def _integer(text, default):
    if text is None or not text.strip():
        if default is None:
            raise ValueError('Empty floor marker')
        return default
    value = text.strip()
    if not re.fullmatch(r'[+-]?[0-9]+', value):
        raise ValueError('Invalid floor integer')
    return int(value)


def _validated_rows(payload: bytes):
    """Validate the same marker contract as both runtime XML loaders."""
    root = ET.fromstring(payload)
    if root.tag != 'TileDef-array' or any(row.tag != 'TileDef' for row in root):
        raise ValueError('Expected TileDef-array')
    if len(root) > 249:
        raise ValueError('Standard floor definitions exceed available non-reserved overlay slots')
    parsed = []
    required = ('colour', 'unknown', 'objectType')
    markers = ('worldBuilderMaterial', 'worldBuilderSourceOverlay')
    for raw, row in enumerate(root, 1):
        for name in required + markers:
            fields = list(row.iter(name))
            if len(fields) != len(row.findall(name)) or len(fields) > 1:
                raise ValueError(f'Invalid or duplicate {name} at floor {raw}')
            if fields and (len(fields[0]) or name in markers and fields[0].text is None):
                raise ValueError(f'Invalid {name} at floor {raw}')
        values = tuple(_integer(row.findtext(name), 0) for name in required)
        if any(value < -2147483648 or value > 2147483647 for value in values) or values[2] not in (0, 1):
            raise ValueError(f'Noncanonical floor values at {raw}')
        material = row.findtext('worldBuilderMaterial')
        source_text = row.findtext('worldBuilderSourceOverlay')
        source = _integer(source_text, None) if source_text is not None else None
        if material is not None and (material != 'base-color-v1' or values[:2] != (0, 0) or source is not None):
            raise ValueError(f'Invalid explicit base-color floor at {raw}')
        if source is not None:
            if source < 1 or source >= raw:
                raise ValueError(f'Invalid source floor at {raw}')
            original = parsed[source - 1]
            if original[2] is not None or original[3] is not None or original[1][:2] != values[:2]:
                raise ValueError(f'Floor partner does not match its original at {raw}')
        parsed.append((row, values, material, source))
    return parsed


def extend(payload: bytes) -> bytes:
    """Complete an imported catalog without renumbering or replacing any row.

    Equivalent generated rows share the exact original source ID and blocking
    state. Matching original rows can be reused except projectile IDs 2/11 and
    transparent non-water floors (which need marked variants for picking).
    """
    rows = _validated_rows(payload)
    additions = []
    partners = {(source, values[2]) for _, values, _, source in rows if source is not None}
    bases = {values[2] for _, values, material, _ in rows if material is not None}
    for raw, (row, values, material, source) in enumerate(rows, 1):
        if material is not None or source is not None:
            continue
        reusable = raw not in (2, 11) and not (values[0] == 12345678 and values[1] != 4)
        for blocking in (0, 1):
            if (raw, blocking) in partners or reusable and values[2] == blocking:
                continue
            partner = deepcopy(row)
            for name, value in zip(('colour', 'unknown', 'objectType'), (values[0], values[1], blocking)):
                field = partner.find(name)
                if field is None:
                    field = ET.SubElement(partner, name)
                field.text = str(value)
            ET.SubElement(partner, 'worldBuilderSourceOverlay').text = str(raw)
            additions.append(partner)
    for blocking in (0, 1):
        if blocking not in bases:
            row = ET.Element('TileDef')
            for name, value in (('colour', '0'), ('unknown', '0'), ('objectType', str(blocking)), ('worldBuilderMaterial', 'base-color-v1')):
                ET.SubElement(row, name).text = value
            additions.append(row)
    if len(rows) + len(additions) > 249:
        raise ValueError(f'Standard floors need {len(additions)} additional slots but only {249 - len(rows)} are available; no definitions were changed')
    if not additions:
        return payload
    closing = b'</TileDef-array>'
    if payload.count(closing) != 1:
        raise ValueError('Expected one TileDef-array closing tag')
    appendix = b''.join(ET.tostring(row, encoding='utf-8') + b'\n' for row in additions)
    return payload.replace(closing, appendix + closing)
