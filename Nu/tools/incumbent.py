"""Launch a registered research incumbent only with its hash-pinned engine."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]

def checked_pair(root,record):
    pair=record['required_pair']
    result=[]
    for kind in ('engine','model'):
        path=(root/pair[kind]).resolve()
        if not path.is_relative_to(root.resolve()):raise RuntimeError('artifact escapes workspace')
        if hashlib.sha256(path.read_bytes()).hexdigest()!=pair[kind+'_sha256']:
            raise RuntimeError('incumbent '+kind+' hash mismatch')
        result.append(str(path))
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    record=json.loads((ROOT/'Nu/incumbents/64-linear.json').read_text())
    engine,model=checked_pair(ROOT,record)
    if args.check:
        print(json.dumps(record,indent=2))
        return 0
    return subprocess.call([engine,'--model',model])

if __name__=='__main__':raise SystemExit(main())
