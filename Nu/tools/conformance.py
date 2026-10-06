"""Differential move-set and result checks against the pinned offline reference."""
import argparse
import json
from pathlib import Path
import random
from evidence import atomic_json, digest, REPETITION_POLICY
from train import response, resource_guard
from genseki.uhp import UhpProcess

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--teacher',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--games',type=int,default=10)
    p.add_argument('--plies',type=int,default=100);p.add_argument('--replay',type=Path)
    args=p.parse_args();rng=random.Random(77321)
    engine=UhpProcess([str(args.engine)]);teacher=None;checked=0;repetitions=0
    evidence=dict(engine_sha256=digest(args.engine),teacher_sha256=digest(args.teacher),policy=REPETITION_POLICY,passed=False)
    game_string='Base'
    try:
        teacher=UhpProcess([str(args.teacher)])
        for game in range(args.games):
            resource_guard();game_string=response(engine,'newgame Base')[0]
            replay=[]
            if args.replay:
                saved=json.loads(args.replay.read_text())
                game_string=saved['games'][0];response(engine,'newgame '+game_string)
                reference=response(teacher,'inspect '+game_string)[0][5:]
                assert reference.split(';')[1]=='Draw' and response(engine,'nu-matchdraw')[0]=='True'
                repetitions+=1;break
            for ply in range(args.plies):
                inspection=response(teacher,'inspect '+game_string)
                reference=inspection[0][5:]
                actual=game_string.split(';')[1]
                if response(engine,'nu-matchdraw')[0]=='True':
                    assert reference.split(';')[1]=='Draw';repetitions+=1;break
                assert reference.split(';')[1]==actual,(actual,reference)
                if actual not in ('NotStarted','InProgress'):break
                native=response(engine,'validmoves')[0].split(';')
                expert=inspection[1][6:].split(';')
                native_ids={response(engine,'nu-moveid '+move)[0] for move in native}
                expert_ids={response(engine,'nu-moveid '+move)[0] for move in expert}
                assert native_ids==expert_ids,dict(missing=list(expert_ids-native_ids),extra=list(native_ids-expert_ids))
                checked+=1;move=rng.choice(native);replay.append(move)
                game_string=response(engine,'play '+move)[0]
        evidence.update(passed=True,positions=checked,repetitions=repetitions,games=args.games)
    except BaseException as error:
        evidence.update(error=repr(error),game_string=game_string)
        atomic_json(args.output,evidence);raise
    finally:
        engine.close()
        if teacher:teacher.close()
    atomic_json(args.output,evidence);print(json.dumps(evidence))

if __name__=='__main__':main()
