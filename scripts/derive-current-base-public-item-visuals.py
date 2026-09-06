#!/usr/bin/env python3
"""Derive DATA from one reviewed public Java blob; never compile/evaluate Java.

Read the exact public EntityHandler blob on stdin. The closed parser supports
only constructor literals and the four reviewed false Base condition flags.
Output is deterministic JSON. No target checkout or execution is required.
"""

import hashlib
import json
import re
import sys

SOURCE_SHA256 = '25f7c54a8d4f8fb76ed2a680538404f4e80ccf764451cd9d84c1313e761e2b62'
FLAGS = {'Config.' + name: False for name in (
    'S_WANT_EQUIPMENT_TAB', 'S_WANT_CUSTOM_SPRITES',
    'S_IMPROVED_ITEM_OBJECT_NAMES', 'S_WANT_EXTENDED_CATS_BEHAVIOR')}
LEX = re.compile(r'\s*("(?:\\.|[^"\\])*"|0[xX][0-9a-fA-F]+|[0-9]+|'
                 r'Config\.[A-Z_]+|true|false|[?:(),!+\-])')


class Literals:
    def __init__(self, text):
        self.tokens = []
        offset = 0
        while offset < len(text):
            match = LEX.match(text, offset)
            if not match:
                raise ValueError('unsupported literal syntax at ' + text[offset:offset + 80])
            self.tokens.append(match.group(1))
            offset = match.end()
        self.at = 0

    def peek(self):
        return self.tokens[self.at] if self.at < len(self.tokens) else None

    def take(self, expected=None):
        value = self.peek()
        if value is None or expected is not None and value != expected:
            raise ValueError('unexpected literal token ' + str(value))
        self.at += 1
        return value

    def atom(self):
        token = self.take()
        if token == '(':
            value = self.expression()
            self.take(')')
            return value
        if token in ('!', '-'):
            value = self.atom()
            if token == '!':
                if type(value) is not bool:
                    raise ValueError('non-boolean condition')
                return not value
            if type(value) is not int:
                raise ValueError('non-integer negation')
            return -value
        if token.startswith('"'):
            # The reviewed Java literals use JSON-compatible string escapes.
            return json.loads(token)
        if token in FLAGS:
            return FLAGS[token]
        if token in ('true', 'false'):
            return token == 'true'
        if re.fullmatch(r'0[xX][0-9a-fA-F]+|[0-9]+', token):
            return int(token, 16 if token.lower().startswith('0x') else 10)
        raise ValueError('unsupported literal ' + token)

    def expression(self):
        value = self.atom()
        while self.peek() == '+':
            self.take('+')
            right = self.atom()
            if type(value) is str and type(right) is str:
                value += right
            elif type(value) is int and type(right) is int:
                value += right
            else:
                raise ValueError('unsupported mixed literal addition')
        if self.peek() == '?':
            if type(value) is not bool:
                raise ValueError('non-boolean ternary')
            self.take('?')
            yes = self.expression()
            self.take(':')
            no = self.expression()
            return yes if value else no
        return value

    def arguments(self):
        result = [self.expression()]
        while self.peek() == ',':
            self.take(',')
            result.append(self.expression())
        if self.peek() is not None:
            raise ValueError('unconsumed constructor text')
        return result


def derive(payload):
    if len(payload) > 1000000 or hashlib.sha256(payload).hexdigest() != SOURCE_SHA256:
        raise ValueError('not the exact reviewed public EntityHandler source')
    text = payload.decode('utf-8', errors='strict')
    start = text.index('private static void loadItemDefinitions()')
    end = text.index('private static void loadAnimationDefinitions()', start)
    text = text[start:end]
    text = re.sub(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/',
                  lambda m: m[0] if m[0].startswith('"') else '', text, flags=re.S)
    rows = []
    for line in text.splitlines():
        if 'items.add(new ItemDef(' not in line:
            continue
        match = re.fullmatch(r'\s*items\.add\(new ItemDef\((.*)\)\);\s*', line)
        if not match:
            raise ValueError('unreviewed constructor statement')
        args = Literals(match[1]).arguments()
        if len(args) not in (14, 15) or args[-1] != len(rows):
            raise ValueError('non-contiguous item constructor registry: ' + str((len(rows), args)))
        rows.append({'id': args[-1], 'authenticSpriteId': args[4],
                     'spriteLocation': args[5], 'pictureMask': args[9],
                     'blueMask': args[10] if len(args) == 15 else 0})
    if len(rows) != 1593:
        raise ValueError('incomplete stock item registry')
    # These are the only unconditional post-constructor visual mutations in
    # the exact reviewed methods. Conditional changes only alter display names.
    mutations = re.findall(r'items\.get\((\d+)\)\.spriteLocation = ("[^"]+");', text)
    if len(mutations) != 21:
        raise ValueError('unreviewed post-constructor visual mutation set')
    for item, location in mutations:
        rows[int(item)]['spriteLocation'] = json.loads(location)
    return {'schemaVersion': 1, 'manifestType': 'current-base-public-item-visuals',
            'sourceSha256': SOURCE_SHA256, 'flags': FLAGS, 'items': rows}


if __name__ == '__main__':
    document = derive(sys.stdin.buffer.read(1000001))
    print(json.dumps(document, ensure_ascii=False, separators=(',', ':')))
