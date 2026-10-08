"""Pin instrumentation only after exact Gen 1 fixed-depth search parity."""
import argparse
import json
from pathlib import Path
import random
import re
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from genseki.uhp import UhpProcess
from train import response,resource_guard
from evidence import atomic_json,digest
from gen1_teacher import Gen1Teacher


def main():
    p=argparse.ArgumentParser()
    for name in ('teacher','gen1','referee','output'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    if args.output.exists():raise RuntimeError('use fresh teacher verification evidence')
    pin=json.loads((ROOT/'Alpha/reports/gen2/gen1.json').read_text())
    if digest(args.gen1)!=pin['sha256']:raise RuntimeError('Gen 1 reference pin mismatch')
    if digest(args.teacher)!=pin['sha256']:raise RuntimeError('teacher must be the frozen Gen 1 executable')
    args.output.mkdir(parents=True)
    with (args.output/'gen1-stderr.log').open('w',encoding='utf8') as log,(args.output/'teacher-stderr.log').open('w+',encoding='utf8') as tlog:
        peers=[]
        try:
            for executable,stderr in ((args.gen1,log),(args.referee,None)):
                peers.append(UhpProcess([str(executable.resolve())],stderr=stderr))
            original,referee=peers
            adapter=Gen1Teacher(args.teacher,tlog);peers.append(adapter)
            teacher=adapter.peer
            for peer in (original,):
                for option in ('NumThreads 1','TableSizeMiB 16','BackgroundPondering False','RandomOpening False','Verbose True'):
                    response(peer,'options set '+option)
            response(referee,'newgame Base');rng=random.Random(330001);games=[]
            for ply in range(40):
                state=response(referee,'play '+rng.choice(sorted(response(referee,'validmoves')[0].split(';'))))[0]
                if ply>=3 and ply%3==0:games.append(state)
                if state.split(';')[1]!='InProgress':break
            records=[]
            for game in games[:12]:
                resource_guard()
                response(original,'newgame '+game)
                before=(args.output/'gen1-stderr.log').read_text()
                old=response(original,'bestmove depth 3')[0]
                new=adapter.search(game,3,2000)
                stderr=(args.output/'gen1-stderr.log').read_text()[len(before):]
                values=re.findall(r'fullsearch depth 3 .*?value\s+(-?\d+)',stderr)
                nodes=re.search(r'Explored (\d+) nodes to depth (\d+)',stderr)
                if not values or int(values[-1])!=new['raw_score'] or not nodes or int(nodes[2])!=new['completed_depth']:
                    raise RuntimeError('Gen 1 teacher score/node/depth mismatch')
                positions=[]
                for peer,move in ((original,old),(teacher,new['move'])):
                    child=response(peer,'play '+move)[0]
                    positions.append(response(referee,'genseki-validate-game '+child)[0])
                if positions[0]!=positions[1]:raise RuntimeError('Gen 1 teacher move mismatch')
                records.append(dict(game=game,score=new['raw_score'],reference_nodes=int(nodes[1]),
                                    teacher_nodes=new['nodes'],depth=3,pv=new['pv']))
            if len(records)!=12:raise RuntimeError('need twelve teacher verification roots')
            report=dict(gen1_sha256=digest(args.gen1),teacher_sha256=digest(args.teacher),
                        referee_sha256=digest(args.referee),passed=True,positions=12,records=records,
                        contract='identical frozen executable; equal scores and reconstructed moves',
                        node_counts='measured, not required identical across separate Gen 1 processes')
            atomic_json(args.output/'parity.json',report)
            print(json.dumps(report),flush=True)
        finally:
            for peer in peers:peer.close()


if __name__=='__main__':
    from research_job import run
    run(main)
