"""Publish immutable search evidence without host-specific invocation paths."""
import argparse
import json
from pathlib import Path,PureWindowsPath
import re

from evidence import atomic_json,digest


def public_copy(value):
    if isinstance(value,list):return [public_copy(item) for item in value]
    if isinstance(value,dict):
        return {key:([(PureWindowsPath(item).name if '\\' in item else Path(item).name) for item in item_value] if key=='invocation' else public_copy(item_value))
                for key,item_value in value.items()}
    if isinstance(value,str) and (re.search(r'[A-Za-z]:[\\/]',value) or '/Users/' in value):
        raise RuntimeError('host-specific path outside invocation; do not publish')
    return value


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise RuntimeError('evidence namespace is immutable')
    copies={};manifest=[];summaries=[]
    for source in sorted(args.directory.glob('*.json')):
        value=json.loads(source.read_text());copies[source.name]=public_copy(value)
        if isinstance(value,dict) and isinstance(value.get('games'),list):
            games=value['games'];kinds=sorted({row['termination'] for row in games})
            summaries.append(dict(report=source.name,completed=value['completed'],rejected=value['rejected'],points=value['points'],games=len(games),
                terminations={kind:sum(g['termination']==kind for g in games) for kind in kinds},
                own_timeouts=sum(g['termination']=='timeout' and g['timeout_side']=='Nu' for g in games),
                opponent_timeouts=sum(g['termination']=='timeout' and g['timeout_side']=='Opponent' for g in games)))
        manifest.append(dict(file=source.name,private_original_sha256=digest(source)))
    args.output.mkdir(parents=True)
    for row in manifest:
        target=args.output/row['file'];atomic_json(target,copies[row['file']]);row['public_sha256']=digest(target)
    atomic_json(args.output/'export.json',dict(version=1,redaction='invocation-filenames-only-v1',files=manifest,summaries=summaries,
                sealed_qualification=False,promotion=False))
    print(json.dumps(summaries))


if __name__=='__main__':main()
