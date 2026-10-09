"""Atomic evidence writes and shared match-policy metadata."""
import hashlib
import json
import os
from pathlib import Path

REPETITION_POLICY = 'nokamute-1.0.3-stride4-window32-v1'
NOKAMUTE_REVISION = 'c9ab65e0d9f496fd8735096ae37babc8bb50a57c'
NOKAMUTE_SHA256 = '4936c30a84df62589b1902a0fe3c4fbdd71674f2c16461e6c5a4887352990d13'

def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()

def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.pending')
    with pending.open('w', encoding='utf8', newline='\n') as handle:
        json.dump(value, handle, indent=2)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(pending, path)
