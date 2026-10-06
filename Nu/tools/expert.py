"""Pinned expert demonstrations, genuine outcomes, and legal move preferences."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
from train import response, resource_guard
from genseki.uhp import UhpProcess

def active(engine):
    return [list(map(int,line.split(':')[1].split())) for line in response(engine,'nu-features')[:2]]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--expert',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--games',type=int,default=60)
    p.add_argument('--milliseconds',type=int,default=20);p.add_argument('--cap',type=int,default=160)
    p.add_argument('--evaluator',type=Path)
    args=p.parse_args()
    if args.output.exists():raise RuntimeError('refusing to replace an existing corpus')
    if args.games<5 or args.games>500 or not 1<=args.milliseconds<=250 or not 1<=args.cap<=256:raise RuntimeError('invalid bounded corpus limits')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    expert_hash=hashlib.sha256(args.expert.read_bytes()).hexdigest()
    native=UhpProcess([str(args.engine)])
    try:expert=UhpProcess([str(args.expert)])
    except BaseException:native.close();raise
    teacher=None
    schema=int(response(native,'nu-feature-schema')[0])
    rng=random.Random(44191);pending=args.output.with_suffix('.pending')
    try:
        if args.evaluator:teacher=UhpProcess([str(args.evaluator)])
        response(expert,'options set NumThreads 1');response(expert,'options set BackgroundPondering False')
        response(expert,'options set RandomOpening False');response(expert,'options set TableSizeMiB 16')
        with pending.open('x',encoding='utf8') as output:
            for game in range(args.games):
                resource_guard();response(native,'newgame Base');response(expert,'newgame Base')
                rows=[];outcome=None;game_string='Base';termination='ply_cap'
                for ply in range(args.cap):
                    moves=response(native,'validmoves')[0].split(';')
                    chosen=response(expert,f'bestmove depthorseconds 32 {args.milliseconds/1000}')[0]
                    row=dict(game=game,ply=ply,features=active(native),feature_schema=schema,teacher_move=chosen,search_cp=0,depth=0,nodes=0,
                             position=response(native,'nu-position')[0],game_string=game_string,expert=True,mover=1 if ply%2==0 else -1)
                    if teacher:
                        row['teacher_cp']=int(response(teacher,'eval '+game_string)[0].split()[1])*4
                    # The same parent's two legal children establish a local preference.
                    alternatives=[move for move in moves if move!=chosen]
                    if alternatives and ply>=4:
                        response(native,'play '+chosen);row['preferred_features']=active(native);row['preferred_position']=response(native,'nu-position')[0];response(native,'undo')
                        alternative=rng.choice(alternatives)
                        response(native,'play '+alternative);row['alternative_features']=active(native);row['alternative_position']=response(native,'nu-position')[0];response(native,'undo')
                    rows.append(row)
                    move=rng.choice(moves) if ply<4 or rng.random()<.08 else chosen
                    results=[response(engine,'play '+move)[0] for engine in (native,expert)]
                    states=[text.split(';')[1] for text in results]
                    game_string=results[0]
                    if states[0]!=states[1]:
                        evidence=dict(states=states,move=move,games=results,position=response(native,'nu-position')[0])
                        args.output.with_suffix('.divergence.json').write_text(json.dumps(evidence,indent=2))
                        if states==['InProgress','Draw'] and int(response(native,'nu-repetition')[0])>=3:
                            termination='expert_repetition';break
                        raise RuntimeError('unexplained rules/result divergence; evidence saved')
                    if states[0]!='InProgress':
                        outcome={'WhiteWins':1,'BlackWins':-1,'Draw':0}[states[0]];termination='natural';break
                for row in rows:
                    row.update(outcome=outcome,termination=termination,
                               source=expert_hash,seed=44191,expert_ms=args.milliseconds)
                    output.write(json.dumps(row)+'\n')
                output.flush()
                print(f'expert game {game+1}/{args.games}: {len(rows)} plies, outcome={outcome}',flush=True)
        os.replace(pending,args.output)
    finally:
        native.close();expert.close()
        if teacher:teacher.close()
if __name__=='__main__':main()
