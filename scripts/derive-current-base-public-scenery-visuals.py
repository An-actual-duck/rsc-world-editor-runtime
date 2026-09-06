#!/usr/bin/env python3
"""Extract reviewed public client model-name DATA; never evaluate Java."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys

spec = importlib.util.spec_from_file_location('public_literals', Path(__file__).with_name('derive-current-base-public-item-visuals.py'))
literals = importlib.util.module_from_spec(spec)
spec.loader.exec_module(literals)
# This source flag changes only the two flax commands, never its model name.
# Commands/geometry are not emitted by this visual-only extractor.
literals.FLAGS['Config.S_BATCH_PROGRESSION'] = False


def derive(payload):
    if len(payload) > 1000000 or hashlib.sha256(payload).hexdigest() != literals.SOURCE_SHA256:
        raise ValueError('not the exact reviewed public EntityHandler source')
    text = payload.decode('utf-8', errors='strict')
    text = text[text.index('private static void loadGameObjectDefinitionsA()'):text.index('public static void load(boolean loadMembers)')]
    text = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/',
                  lambda m: m[0] if m[0].startswith('"') else '', text, flags=re.S)
    rows, counter = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if line == 'int i = 0;':
            counter = 0
        elif line == 'int i = objects.size();':
            counter = len(rows)
        elif 'objects.add(new GameObjectDef(' in line:
            match = re.fullmatch(r'objects\.add\(new GameObjectDef\((.*),\s*(i\+\+|\+\+i|i\s*=\s*[0-9]+)\)\);', line)
            if not match or counter is None:
                raise ValueError('unreviewed scenery constructor')
            args = literals.Literals(match[1]).arguments()
            if len(args) != 9 or not isinstance(args[8], str):
                raise ValueError('unreviewed scenery fields')
            expression = match[2]
            if expression == 'i++':
                identity = counter
                counter += 1
            elif expression == '++i':
                counter += 1
                identity = counter
            else:
                counter = identity = int(expression.split('=')[1])
            if identity != len(rows):
                raise ValueError('non-contiguous scenery identity')
            rows.append({'id': identity, 'objectModel': args[8]})
    if len(rows) != 1296:
        raise ValueError('incomplete public scenery registry')
    return {'schemaVersion': 1, 'manifestType': 'current-base-public-scenery-visuals',
            'sourceSha256': literals.SOURCE_SHA256, 'scenery': rows}


if __name__ == '__main__':
    print(json.dumps(derive(sys.stdin.buffer.read(1000001)), ensure_ascii=False, separators=(',', ':')))
