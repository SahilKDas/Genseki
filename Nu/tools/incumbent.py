"""Launch a registered research incumbent only with its hash-pinned engine."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from genseki.uhp import UhpProcess


def verified_settings(record):
    settings=record.get('uhp_settings',{})
    limits={'Threads':(1,12),'TableMiB':(1,256),'ThreatPlies':(0,4)}
    booleans={'BackgroundPondering','LateMoveReductions','DeadlineGuard','CooperativeOrdering','RootPVS'}
    for name,value in settings.items():
        if name in limits:
            if type(value)!=int or not limits[name][0]<=value<=limits[name][1]:raise RuntimeError('invalid incumbent option')
        elif name in booleans:
            if type(value)!=bool:raise RuntimeError('invalid incumbent boolean')
        else:raise RuntimeError('unsupported incumbent option')
    return settings

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
    parser.add_argument('--record',type=Path,default=ROOT/'Nu/incumbents/64-linear.json')
    args=parser.parse_args()
    record=json.loads(args.record.read_text())
    engine,model=checked_pair(ROOT,record)
    settings=verified_settings(record)
    if args.check:
        print(json.dumps(record,indent=2))
        return 0
    if not settings:return subprocess.call([engine,'--model',model])
    peer=UhpProcess([engine,'--model',model])
    try:
        for name,value in settings.items():
            lines,_=peer.command(f'options {name} {value}',5)
            if any(line.startswith('err ') for line in lines):raise RuntimeError('incumbent option rejected')
        lines,_=peer.command('info',5)
        print('\n'.join(lines),flush=True)
        for line in sys.stdin:
            if line.strip()=='exit':break
            lines,_=peer.command(line.rstrip('\r\n'),65 if line.startswith('bestmove ') else 5)
            print('\n'.join(lines),flush=True)
    finally:peer.close()
    return 0

if __name__=='__main__':raise SystemExit(main())
