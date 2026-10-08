"""Immutable repair of the historical canonical corpus/index; no optimizer reuse."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from genseki.uhp import UhpProcess
from evidence import atomic_json,digest
from train import response,resource_guard
import learning


def main():
    p=argparse.ArgumentParser()
    for name in ('index','corpus','engine','referee','output'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise RuntimeError('use a fresh immutable repair namespace')
    identity=dict(index_sha256=digest(args.index),corpus_sha256=digest(args.corpus),
                  engine_sha256=digest(args.engine),referee_sha256=digest(args.referee))
    with sqlite3.connect(args.index.resolve().as_uri()+'?mode=ro',uri=True) as db:
        original=[(json.loads(payload),split) for payload,split in db.execute('select payload,split from samples')]
    args.output.mkdir(parents=True)
    rows=[]
    inputs=[json.loads(line) for line in args.corpus.read_text().splitlines()]
    openings={}
    for row in inputs:
        game=row.get('game_string','').split(';')
        if len(game)>=7:openings[(row['source'],row['seed'],row['game'])]=game[3:7]
    encoder=UhpProcess([str(args.engine),'--feature-schema','6'])
    referee=None
    try:
        referee=UhpProcess([str(args.referee)])
        for source in inputs:
            resource_guard();row=dict(source)
            if row.get('feature_schema') not in (5,6):raise RuntimeError('unexpected historical canonical schema')
            response(encoder,'nu-loadposition '+row['position'])
            features=[list(map(int,x.split(':',1)[1].split())) for x in response(encoder,'nu-features')[:2]]
            if row['features']!=features:raise RuntimeError('historical feature contract is not canonical schema 6')
            row['feature_schema']=6
            game=openings.get((row['source'],row['seed'],row['game']))
            if not game:raise RuntimeError('opening replay missing; cannot repair grouping safely')
            opening='Base;InProgress;White[3];'+';'.join(game)
            row['opening_position']=response(referee,'genseki-validate-game '+opening)[0]
            for target,position in (('preferred_features','preferred_position'),('alternative_features','alternative_position')):
                if target in row:
                    response(encoder,'nu-loadposition '+row[position])
                    if row[target]!=[list(map(int,x.split(':',1)[1].split())) for x in response(encoder,'nu-features')[:2]]:
                        raise RuntimeError('historical child contract mismatch')
            for child in row.get('alternatives',[]):
                response(encoder,'nu-loadposition '+child['position'])
                if child['features']!=[list(map(int,x.split(':',1)[1].split())) for x in response(encoder,'nu-features')[:2]]:
                    raise RuntimeError('historical candidate contract mismatch')
            rows.append(row)
    finally:
        encoder.close()
        if referee:referee.close()
    corpus=args.output/'schema6-repaired.jsonl'
    corpus.write_text('\n'.join(json.dumps(row,separators=(',',':')) for row in rows)+'\n')
    db=learning.index_corpus([corpus],args.output/'index.sqlite')
    try:
        repaired={json.loads(payload)['position']:split for payload,split in db.execute('select payload,split from samples')}
    finally:db.close()
    report=dict(identity,position_key_version='base-symmetry-opening-v2',old_samples=len(original),
                repaired_samples=len(repaired),removed_samples=sum(row['position'] not in repaired for row,_ in original),
                changed_splits=sum(row['position'] in repaired and repaired[row['position']]!=split for row,split in original),
                previous_validation_status='pre-repair; not leakage-controlled',optimizer_resume_authorized=False,
                repaired_corpus_sha256=digest(corpus),repaired_index_sha256=digest(args.output/'index.sqlite'))
    if digest(args.index)!=identity['index_sha256'] or digest(args.corpus)!=identity['corpus_sha256']:
        raise RuntimeError('historical inputs changed')
    atomic_json(args.output/'repair.json',report)
    print(json.dumps(report),flush=True)


if __name__=='__main__':
    from research_job import run
    run(main)
