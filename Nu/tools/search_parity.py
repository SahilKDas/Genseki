"""Check bounded threat-search scores against a frozen pre-optimization engine."""
import argparse
from contextlib import ExitStack,closing
import json
from pathlib import Path
import shutil

from evidence import atomic_json,digest
from research_job import check_deadline,run
from train import resource_guard,response
from genseki.uhp import UhpProcess


def main():
    p=argparse.ArgumentParser()
    for name in ('engine','reference','model','roots','directory'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--depth',type=int,default=1)
    p.add_argument('--threats',type=int,nargs='+',default=[1,2])
    args=p.parse_args()
    if not 1<=args.depth<=4 or any(t not in range(5) for t in args.threats):raise ValueError('invalid parity limits')
    if args.directory.exists():raise RuntimeError('immutable search parity namespace exists')
    resource_guard();args.directory.mkdir(parents=True);pins={};rows=[]
    for name,source in [('candidate',args.engine),('reference',args.reference),('model',args.model)]:
        target=args.directory/(name+('.nnue' if name=='model' else '.exe'))
        shutil.copy2(source,target);pins[name]=digest(target)
    shutil.copy2(args.roots,args.directory/'roots.json');pins['roots']=digest(args.directory/'roots.json')
    roots=json.loads((args.directory/'roots.json').read_text())
    try:
        with ExitStack() as stack:
            peers=[stack.enter_context(closing(UhpProcess([str((args.directory/(name+'.exe')).resolve()),'--model',str((args.directory/'model.nnue').resolve())]))) for name in ('candidate','reference')]
            for peer in peers:
                for text in ('options Threads 1','options RootPVS False','options LateMoveReductions False'):
                    response(peer,text)
            for threats in args.threats:
                for root in roots:
                    check_deadline();resource_guard();results=[]
                    for peer in peers:
                        response(peer,'options ThreatPlies '+str(threats))
                        response(peer,'nu-loadposition '+root['position'])
                        legal=response(peer,'validmoves')[0].split(';')
                        lines,_=peer.command(f'bestmove depthorseconds {args.depth} 10',15)
                        if not lines or lines[0] not in legal:raise RuntimeError('illegal parity reply')
                        info=response(peer,'nu-searchinfo')[0].split()
                        completed_depth=int(info[1]);score=int(info[5])
                        if completed_depth!=args.depth and not (0<completed_depth<args.depth and abs(score)>90000):
                            raise RuntimeError('parity depth did not complete')
                        if response(peer,'nu-position')[0]!=root['position']:raise RuntimeError('parity search mutated root')
                        results.append(score)
                    if results[0]!=results[1]:raise RuntimeError('threat-search score diverged')
                    rows.append(dict(category=root['category'],depth=args.depth,threat_plies=threats,score=results[0]))
        for name,sha in pins.items():
            path=args.directory/('roots.json' if name=='roots' else name+('.nnue' if name=='model' else '.exe'))
            if digest(path)!=sha:raise RuntimeError('parity artifact changed')
        atomic_json(args.directory/'parity.json',dict(completed=True,pins=pins,rows=rows,scores_equal=True))
        print(f'{len(rows)} threat-search scores matched')
    except BaseException as error:
        atomic_json(args.directory/'failure.json',dict(completed=False,pins=pins,rows=rows,error_type=type(error).__name__))
        raise


if __name__=='__main__':run(main)
