"""Compare optimized Nu legal play against an immutable previous native engine."""
import argparse
from contextlib import ExitStack,closing
from pathlib import Path
import random
import shutil

from evidence import atomic_json,digest
from research_job import check_deadline,run
from train import resource_guard,response
from genseki.uhp import UhpProcess


def main():
    p=argparse.ArgumentParser()
    for name in ('engine','reference','model','directory'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    if args.directory.exists():raise RuntimeError('immutable parity namespace exists')
    resource_guard();args.directory.mkdir(parents=True)
    pins={}
    for name,source in [('candidate',args.engine),('reference',args.reference),('model',args.model)]:
        target=args.directory/(name+('.nnue' if name=='model' else '.exe'))
        shutil.copy2(source,target);pins[name]=digest(target)
    positions=0;plies=0;records=[]
    try:
        with ExitStack() as stack:
            peers=[stack.enter_context(closing(UhpProcess([str((args.directory/(name+'.exe')).resolve()),'--model',str((args.directory/'model.nnue').resolve())]))) for name in ('candidate','reference')]
            for peer in peers:response(peer,'options Threads 1')
            for game in range(16):
                game_plies=0
                resource_guard();rng=random.Random(100901+game)
                for peer in peers:state=response(peer,'newgame Base')[0]
                for ply in range(80):
                    check_deadline()
                    if state.split(';')[1] not in ('NotStarted','InProgress'):break
                    legal=[response(peer,'validmoves')[0].split(';') for peer in peers]
                    if legal[0]!=legal[1]:raise RuntimeError('legal move list diverged')
                    board=[response(peer,'nu-position')[0] for peer in peers]
                    if board[0]!=board[1]:raise RuntimeError('position diverged')
                    positions+=1;move=rng.choice(legal[0])
                    states=[response(peer,'play '+move)[0] for peer in peers]
                    if states[0]!=states[1]:raise RuntimeError('replay or result diverged')
                    state=states[0];plies+=1;game_plies+=1
                    if ply%11==10:
                        states=[response(peer,'undo')[0] for peer in peers]
                        if states[0]!=states[1]:raise RuntimeError('undo diverged')
                        states=[response(peer,'play '+move)[0] for peer in peers]
                        if states[0]!=states[1]:raise RuntimeError('replayed move diverged')
                records.append(dict(seed=100901+game,plies=game_plies,result=state.split(';')[1]))
            fixtures=['G1|w|8|4|4|0,0=wQ,bB1;1,0=bQ',
                      'G1|b|10|5|5|0,0=wQ,wB1,bB1;1,0=bQ;1,-1=wA1;-1,0=bA1',
                      'G1|w|8|4|4|0,0=wQ;1,0=wA1,bB1;2,0=bQ',
                      'G1|w|12|6|6|0,0=wQ,wB1,bB1,wB2,bB2;1,0=bQ',
                      'G1|b|12|6|6|0,0=wQ,wB1,bB1,wB2,bB2;1,0=bQ']
            for fixture in fixtures:
                for peer in peers:response(peer,'nu-loadposition '+fixture)
                if response(peers[0],'validmoves')!=response(peers[1],'validmoves'):raise RuntimeError('stack/pass fixture diverged')
                positions+=1
        if any(digest(args.directory/(name+('.nnue' if name=='model' else '.exe')))!=sha for name,sha in pins.items()):
            raise RuntimeError('parity artifact changed')
        atomic_json(args.directory/'parity.json',dict(completed=True,pins=pins,positions=positions,plies=plies,records=records,legal_lists_equal=True,undo_replay_equal=True))
        print(f'{positions} positions / {plies} plies matched')
    except BaseException as error:
        atomic_json(args.directory/'failure.json',dict(pins=pins,positions=positions,plies=plies,error_type=type(error).__name__))
        raise


if __name__=='__main__':run(main)
