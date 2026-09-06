#!/usr/bin/env python3
"""One reviewed Base-only archive augmentation; no guessed model aliases."""
import hashlib
import sys

SOURCE_SHA256 = '0041565749f14b211d6eabc5750b01d7ee168de148dae85d463356620d08c010'
PLACEHOLDER_NAME = 'runiteruck1.ob3'
PLACEHOLDER_BYTES = bytes(4)  # OB3: zero vertices, zero faces.


def name_hash(name):
    value = 0
    for char in name.upper():
        value = (value * 61 + ord(char) - 32) & 0xffffffff
    return value


def entries(payload):
    if len(payload) < 8 or len(payload) > 2 * 1024 * 1024:
        raise ValueError('unbounded public model archive')
    size = int.from_bytes(payload[:3], 'big')
    if payload[:3] != payload[3:6] or size != len(payload) - 6:
        raise ValueError('public model archive must be exact uncompressed container')
    data = payload[6:]
    count = int.from_bytes(data[:2], 'big')
    if count not in (501, 502):
        raise ValueError('unexpected public model entry count')
    offset = 2 + count * 10
    seen, result = set(), []
    for i in range(count):
        header = data[2 + i * 10:12 + i * 10]
        if len(header) != 10:
            raise ValueError('truncated public model table')
        key = int.from_bytes(header[:4], 'big')
        length = int.from_bytes(header[4:7], 'big')
        packed = int.from_bytes(header[7:], 'big')
        if key in seen or length != packed or offset + packed > len(data):
            raise ValueError('duplicate/case-alias, compressed or truncated public model entry')
        seen.add(key)
        result.append((key, header, data[offset:offset + packed]))
        offset += packed
    if offset != len(data):
        raise ValueError('trailing public model data')
    return result


def transform(payload):
    if hashlib.sha256(payload).hexdigest() != SOURCE_SHA256:
        raise ValueError('not the exact reviewed public model archive')
    original = entries(payload)
    key = name_hash(PLACEHOLDER_NAME)
    if len(original) != 501 or key in {row[0] for row in original}:
        raise ValueError('public placeholder would replace or alias existing model')
    header = key.to_bytes(4, 'big') + len(PLACEHOLDER_BYTES).to_bytes(3, 'big') * 2
    data = (502).to_bytes(2, 'big') + b''.join(row[1] for row in original) + header
    data += b''.join(row[2] for row in original) + PLACEHOLDER_BYTES
    result = len(data).to_bytes(3, 'big') * 2 + data
    if entries(result)[:-1] != original:
        raise ValueError('public model augmentation changed an original entry')
    return result


if __name__ == '__main__':
    sys.stdout.buffer.write(transform(sys.stdin.buffer.read(2 * 1024 * 1024 + 1)))
