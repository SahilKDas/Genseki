"""Explicit, immutable schema-7 to schema-8 conversion; identical features and payload."""
import argparse
import hashlib
from pathlib import Path
import struct

from evidence import atomic_json, digest


def convert(source, output, expected):
    source, output = Path(source), Path(output)
    if digest(source) != expected:
        raise RuntimeError('source checksum differs from the pinned checkpoint')
    if output.exists() or output.with_suffix('.provenance.json').exists():
        raise RuntimeError('refusing to overwrite an existing artifact')
    raw = source.read_bytes()
    if len(raw) < 32 or len(raw) > 8*1024**2:
        raise RuntimeError('invalid source model size')
    magic, schema, features, width, scale, checksum = struct.unpack_from('<8sIIIIQ', raw)
    if magic not in (b'NUNNUE1\0', b'NUNNUE2\0') or schema != 7 or features != 8192 or width not in (64, 128) or scale != 256:
        raise RuntimeError('only verified schema 7 layouts are compatible')
    size = 32+width*4+8192*width*2+(32*2*width*2+32*4+32*2 if magic == b'NUNNUE2\0' else width*2)
    if len(raw) != size:
        raise RuntimeError('model dimensions mismatch')
    actual = 14695981039346656037
    for byte in raw[32:]:
        actual = ((actual ^ byte)*1099511628211) & ((1 << 64)-1)
    if actual != checksum:
        raise RuntimeError('source payload checksum mismatch')
    for bias, in struct.iter_unpack('<i', raw[32:32+width*4]):
        if abs(bias) > 1000000:
            raise RuntimeError('source bias outside native bounds')
    if magic == b'NUNNUE2\0':
        offset = 32+width*4+8192*width*2+32*2*width*2
        if any(abs(bias) > 1000000 for bias, in struct.iter_unpack('<i', raw[offset:offset+32*4])):
            raise RuntimeError('source head bias outside native bounds')
    result = bytearray(raw)
    struct.pack_into('<I', result, 8, 8)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as handle:
        handle.write(result)
    metadata = {'version': 1, 'source_schema': 7, 'schema': 8,
                'source_sha256': expected, 'model_sha256': digest(output),
                'payload_sha256': hashlib.sha256(raw[32:]).hexdigest(),
                'payload_unchanged': True, 'feature_contract': 'schema7-exact-with-bounded-runtime-v1',
                'default_threads': 8, 'retrained': False, 'promoted': False}
    atomic_json(output.with_suffix('.provenance.json'), metadata)
    return metadata


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source-sha256', required=True)
    args = parser.parse_args()
    import json
    print(json.dumps(convert(args.source, args.output, args.source_sha256)))


if __name__ == '__main__':
    main()
