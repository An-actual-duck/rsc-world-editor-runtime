#!/usr/bin/env python3
"""Stage the reviewed map-only source payload from this provider checkout.

This is a provider packaging operation. It never reads or builds a target game.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = Path('server/conf/world-builder/target-map-integration-v1.json')


def stage(output: Path) -> None:
    descriptor = json.loads((ROOT / CONTRACT).read_text(encoding='utf-8'))
    if descriptor['schemaVersion'] != 1 or descriptor['manifestType'] != 'world-builder-target-map-integration':
        raise ValueError('Unsupported target map integration contract')
    payloads = {}
    for adapter in descriptor['adapters']:
        for source in adapter['sources']:
            role = source['scope']
            if role not in ('server', 'client'):
                raise ValueError('Unsupported integration source role')
            relative = Path(source['targetRelativePath'])
            if relative.is_absolute() or '..' in relative.parts or not str(relative).startswith('src/') or relative.suffix != '.java':
                raise ValueError('Unsafe integration source path')
            original = ROOT / ('server' if role == 'server' else 'Client_Base') / relative
            if not original.is_file() or original.is_symlink() or original.resolve() != original:
                raise ValueError('Unsafe provider source')
            payload = original.read_bytes()
            if hashlib.sha256(payload).hexdigest() != source['sha256']:
                raise ValueError('Provider map source drift: ' + str(relative))
            destination = 'server/conf/world-builder/target-map-source/' + role + '/' + relative.as_posix()
            if source['payloadRelativePath'] != destination:
                raise ValueError('Unexpected integration payload path')
            if destination in payloads and payloads[destination] != payload:
                raise ValueError('Conflicting integration payload')
            payloads[destination] = payload
    output = output.absolute()
    if output.is_symlink() or output.resolve() != output:
        raise ValueError('Unsafe provider staging directory')
    payloads[CONTRACT.as_posix()] = (ROOT / CONTRACT).read_bytes()
    # Verify all inputs and destination ancestry before creating any payload.
    for relative in payloads:
        destination = output / relative
        for parent in [destination, *destination.parents]:
            if parent == output.parent:
                break
            if parent.is_symlink():
                raise ValueError('Symlink in provider staging path')
        if destination.exists() and not destination.is_file():
            raise ValueError('Provider staging destination is not a regular file')
    for relative, payload in payloads.items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    args = parser.parse_args()
    stage(args.runtime_root)
