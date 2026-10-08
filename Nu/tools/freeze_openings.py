"""Reserve private qualification openings before data collection; expose only keys."""
import argparse
import json
from pathlib import Path
import random
import secrets
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from evidence import atomic_json,digest
from position_keys import position_key
from train import response
from genseki.uhp import UhpProcess


def opening(peer,seed):
    response(peer,'newgame Base');rng=random.Random(seed);moves=[]
    for _ in range(4):
        move=rng.choice(sorted(response(peer,'validmoves')[0].split(';')))
        game=response(peer,'play '+move)[0];moves.append(move)
    position=response(peer,'genseki-validate-game '+game)[0]
    return dict(seed=seed,moves=moves,game_string=game,position=position,key=position_key(position))


def main():
    p=argparse.ArgumentParser()
    for name in ('referee','directory','teacher-proof'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    if args.directory.exists():raise RuntimeError('opening reservation is immutable; reuse it, never replace it')
    args.directory.mkdir(parents=True)
    peer=UhpProcess([str(args.referee.resolve())])
    try:
        tactical=set()
        proof=json.loads(args.teacher_proof.read_text())
        for row in proof['records']:
            tactical.add(position_key(response(peer,'genseki-validate-game '+row['game'])[0]))
        profile=json.loads((ROOT/'Alpha/reports/profile-suite.json').read_text())
        for row in profile['records']:
            replay=response(peer,'newgame '+row['position'])[0]
            tactical.add(position_key(response(peer,'genseki-validate-game '+replay)[0]))
        development=[opening(peer,310000+i) for i in range(10)]
        used={r['key'] for r in development};qualification=[]
        while len(qualification)<50:
            row=opening(peer,1000000+secrets.randbelow(1<<30))
            if row['key'] in used or row['key'] in tactical:continue
            qualification.append(row);used.add(row['key'])
        sealed=args.directory/'sealed-qualification-openings.json'
        atomic_json(sealed,dict(version=1,kind='reserved-qualification',referee_sha256=digest(args.referee),openings=qualification))
        atomic_json(args.directory/'development-openings.json',dict(version=1,kind='development',openings=development))
        families={r['key'] for r in qualification+development}
        atomic_json(args.directory/'exclusions.json',dict(version=1,key_version='base-symmetry-opening-v2',
                    qualification_count=50,development_count=10,positions=sorted(tactical|families),
                    opening_families=sorted(families),qualification_manifest_sha256=digest(sealed),
                    referee_sha256=digest(args.referee),qualification_seeds_not_exposed=True))
        print(json.dumps(dict(qualification=50,development=10,tactical_keys=len(tactical),
                             exclusions_sha256=digest(args.directory/'exclusions.json'))))
    finally:peer.close()


if __name__=='__main__':
    from research_job import run
    run(main)
