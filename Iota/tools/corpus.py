"""Bounded Alpha teacher collection. No invented score or capped outcome labels."""
from __future__ import annotations
import argparse
import json
import random
import time
from pathlib import Path
from common import ROOT,UhpProcess,command,atomic,digest,guard,acquire_job

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--games',type=int,default=100)
    p.add_argument('--minutes',type=float,default=30)
    p.add_argument('--seed',type=int,default=1701)
    p.add_argument('--max-plies',type=int,default=160)
    p.add_argument('--teacher-ms',type=int,default=500)
    p.add_argument('--teacher',default=str(ROOT.parent/'build/genseki.exe'))
    p.add_argument('--output',default=str(ROOT/'work/corpus.jsonl'))
    args=p.parse_args()
    if args.games<1 or args.minutes<=0 or not 5<=args.max_plies<=160 or not 1<=args.teacher_ms<=500:p.error('invalid limits')
    job=acquire_job();out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    frozen=digest(args.teacher);deadline=time.monotonic()+args.minutes*60
    allrows=[];groups={};games=[]
    if out.exists():
        allrows=[json.loads(x) for x in out.read_text().splitlines()]
        if any(r['teacher_sha256']!=frozen for r in allrows):raise RuntimeError('teacher identity changed; choose a new corpus')
    first_seed=max((int(r['game_id'])+1 for r in allrows),default=args.seed)
    # Transpositions link games to one split. A collision never crosses a split.
    for row in allrows:groups[row['canonical']]=row['split']
    def persist():
        tmp=out.with_suffix('.tmp');tmp.write_text(''.join(json.dumps(x)+'\n' for x in allrows),encoding='utf-8');tmp.replace(out)
        atomic(out.with_suffix('.manifest.json'),dict(teacher_sha256=frozen,corpus_sha256=digest(out),positions=len(allrows),games=games,complete=len(games)==args.games,teacher_ms=args.teacher_ms,max_plies=args.max_plies,label_policy='Alpha bestmove one-hot; natural outcomes only; no teacher numeric value exposed'))
    teacher=UhpProcess([args.teacher])
    try:rules=UhpProcess([str(ROOT/'build/iota.exe')])
    except BaseException:teacher.close();raise
    try:
        for index in range(args.games):
            if time.monotonic()>deadline-2:break
            guard();seed=first_seed+index;rng=random.Random(seed);rows=[]
            command(teacher,'newgame Base');current,_=command(rules,'newgame Base');game=current[0]
            split=('validation' if seed%10==8 else 'test' if seed%10==9 else 'train')
            family=None;reason='ply_cap'
            for ply in range(args.max_plies):
                if time.monotonic()>deadline-2:reason='deadline';break
                legal,_=command(rules,'validmoves');moves=legal[0].split(';')
                if ply<4:chosen=rng.choice(moves)
                else:
                    response,_=command(teacher,f'bestmove time 00:00:00.{args.teacher_ms:03d}',2)
                    chosen=response[-1];idx,_=command(rules,'iota-index '+chosen)
                    canonical,_=command(rules,'iota-canonical')
                    policy=[0.]*len(moves);policy[int(idx[0])]=1.
                    rows.append(dict(game=game,game_id=str(seed),opening_family=family,
                                     canonical=canonical[0],policy=policy,wdl=None,split=split,
                                     teacher_sha256=frozen,label_kind='teacher_bestmove'))
                command(teacher,'pass' if chosen=='pass' else 'play '+chosen)
                current,_=command(rules,'pass' if chosen=='pass' else 'play '+chosen);game=current[0]
                if ply==3:family=game
                result=game.split(';')[1]
                if result in ('WhiteWins','BlackWins','Draw'):reason='terminal';break
            if reason=='deadline':
                atomic(out.with_suffix('.partial.json'),dict(seed=seed,game=game,reason=reason));break
            if rows:
                collisions={groups[r['canonical']] for r in rows if r['canonical'] in groups}
                # Drop cross-split bridge games rather than leaking transpositions.
                if len(collisions)>1:continue
                if collisions:split=next(iter(collisions))
                for row in rows:
                    row['split']=split;groups[row['canonical']]=split
                    if reason=='terminal':
                        side=row['game'].split(';')[2].startswith('White')
                        row['wdl']=[0.,1.,0.] if result=='Draw' else ([1.,0.,0.] if (result=='WhiteWins')==side else [0.,0.,1.])
                allrows.extend(rows)
            games.append(dict(seed=seed,reason=reason,positions=len(rows)));persist()
            print(games[-1],flush=True)
        if digest(args.teacher)!=frozen:raise RuntimeError('teacher executable changed during collection')
        persist()
    except BaseException as error:
        atomic(out.with_suffix('.failure.json'),dict(error=repr(error),
               seed=locals().get('seed'),game=locals().get('game'),rows=locals().get('rows',[]),
               teacher_sha256=frozen))
        raise
    finally:teacher.close();rules.close()

if __name__=='__main__':main()
