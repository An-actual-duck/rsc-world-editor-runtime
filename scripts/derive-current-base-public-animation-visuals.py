#!/usr/bin/env python3
"""Export one reviewed renderer's implicit animation DATA, never target Java.

The maintained Base profile disables custom sprites and bearded ladies. Only
its unconditional 0..228 registry is implicit; project animation metadata wins.
Whole-source pins make this a reviewed exporter, not a generic Java adapter.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = 'Client_Base/src/com/openrsc/client/entityhandling/EntityHandler.java'
ALLOCATOR_PATH = 'Client_Base/src/orsc/mudclient.java'
SOURCE_SHA256 = 'd02b5cea80eb499d3ec99e78de6edd9096f0f8b71c72597b43928e9d6cd5e9a4'
ALLOCATOR_SHA256 = 'be1f6ea7e49ed7792371292b434c5ac953ce9dddc56f25243749c68d37bc32f3'
PROFILE_ID = 'current-base-authentic-npc-visuals-v1'
FLAGS = {'Config.S_WANT_CUSTOM_SPRITES': False, 'Config.S_ALLOW_BEARDED_LADIES': False}
spec = importlib.util.spec_from_file_location('animation_literals', Path(__file__).with_name('derive-current-base-public-item-visuals.py'))
literals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(literals)


def reviewed(payload, expected):
    if len(payload) > 2000000 or hashlib.sha256(payload).hexdigest() != expected:
        raise ValueError('not the exact reviewed animation source/allocator')
    return payload.decode('utf-8', errors='strict')


def registry_prefix(text):
    start = text.index('private static void loadAnimationDefinitions() {')
    stop = text.index('if (Config.S_WANT_CUSTOM_SPRITES) {', start)
    return text[start:stop]


def allocate(rows):
    """The authentic allocator reserves 27 slots per first case-insensitive name."""
    seen, number = {}, 0
    for row in rows:
        name = row['name'].lower()
        if name not in seen:
            seen[name] = number
            number += 27
            if number == 1998:
                number = 3300
        row['authenticBaseSpriteId'] = seen[name]
    return rows


def derive(source, allocator):
    text = reviewed(source, SOURCE_SHA256)
    reviewed(allocator, ALLOCATOR_SHA256)
    prefix = registry_prefix(text)
    prefix = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/',
                    lambda match: match[0] if match[0].startswith('"') else '', prefix, flags=re.S)
    rows, include, in_branch = [], True, False
    for raw in prefix.splitlines():
        line = raw.strip()
        if not line or line in ('private static void loadAnimationDefinitions() {', 'PROJECT_NPC_ANIMATIONS.clear();'):
            continue
        if line == 'if (Config.S_ALLOW_BEARDED_LADIES) {' and not in_branch:
            in_branch, include = True, False
            continue
        if line == '} else {' and in_branch and not include:
            include = True
            continue
        if line == '}' and in_branch and include:
            in_branch = False
            continue
        match = re.fullmatch(r'animations\.add\(new AnimationDef\((.*)\)\);', line)
        if not match:
            raise ValueError('unsupported reviewed animation statement: ' + line)
        values = literals.Literals(match[1]).arguments()
        if len(values) != 7 or not all(isinstance(values[i], str) for i in (0, 1)):
            raise ValueError('unsupported reviewed animation constructor')
        name, category, colour, gender, combat, special, number = values
        if not re.fullmatch(r'[A-Za-z0-9_]+', name) or category not in ('player', 'equipment', 'npc'):
            raise ValueError('unsupported reviewed animation name/category')
        if any(type(value) is not int for value in (colour, gender, number)) or number != 0:
            raise ValueError('unsupported reviewed animation number/mask')
        if type(combat) is not bool or type(special) is not bool:
            raise ValueError('unsupported reviewed animation frame flags')
        if include:
            rows.append({'animationId': len(rows), 'name': name, 'category': category,
                         'charColour': colour, 'blueMask': 0, 'genderModel': gender,
                         'hasCombatFrames': combat, 'hasSpecialCombatFrames': special,
                         'requiredFrameCount': 27 if special else 18 if combat else 15})
    if in_branch or len(rows) != 229:
        raise ValueError('incomplete reviewed authentic animation registry')
    return {'schemaVersion': 1, 'manifestType': 'current-base-public-animation-visuals',
            'profileId': PROFILE_ID, 'sourceSha256': SOURCE_SHA256,
            'allocatorSourceSha256': ALLOCATOR_SHA256, 'flags': FLAGS, 'animations': allocate(rows)}


if __name__ == '__main__':
    if len(sys.argv) != 1:
        raise SystemExit('usage: derive-current-base-public-animation-visuals.py (reviewed provider sources only)')
    print(json.dumps(derive((ROOT / SOURCE_PATH).read_bytes(), (ROOT / ALLOCATOR_PATH).read_bytes()),
                     ensure_ascii=False, separators=(',', ':')))
