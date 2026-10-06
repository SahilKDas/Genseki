"""Resumable search-teacher/self-play corpus, committed one game at a time."""
import argparse
import json
from pathlib import Path
import random
import time
from evidence import atomic_json, digest, REPETITION_POLICY
from learning import position_key
from train import response, resource_guard
from genseki.uhp import UhpProcess

def storage_guard(root, reserve=64*1024**2):
    import os
    import shutil
    neural=root/'Nu/work'
    paths=[root/'.tmp',neural,root/'data/work',root/'models/work',root/'reports/work']
    paths += [p for p in root.glob('build*') if p.is_dir()]
    def size(path):
        return sum(os.path.getsize(Path(base)/name) for base,_,names in os.walk(path) for name in names)
    sizes=[size(path) if path.exists() else 0 for path in paths]
    if sum(sizes)+reserve>10_000_000_000 or sum(sizes[1:5])+reserve>6_000_000_000:
        raise RuntimeError('temporary storage reserve would exceed device caps')
    if shutil.disk_usage(root).free<reserve+512*1024**2:raise RuntimeError('insufficient free disk reserve')

def collect(args):
    root=Path(__file__).resolve().parents[2]
    resource_guard();storage_guard(root)
    args.directory.mkdir(parents=True,exist_ok=True)
    config=dict(engine_sha256=digest(args.engine),teacher_sha256=digest(args.teacher),seed=args.seed,
                schema=4,milliseconds=args.milliseconds,alternative_ms=args.alternative_ms,cap=args.cap,
                source_model_sha256=digest(args.source_model) if args.source_model else None,
                repetition_policy=REPETITION_POLICY)
    manifest=args.directory/'manifest.json'
    if manifest.exists():
        saved=json.loads(manifest.read_text())
        if saved['config']!=config:raise RuntimeError('collection resume configuration mismatch')
    else:atomic_json(manifest,dict(config=config,games=0,positions=0,completed=False))
    files=sorted(args.directory.glob('game-*.jsonl'))
    count=sum(sum(1 for _ in file.open(encoding='utf8')) for file in files)
    game=len(files);started=time.monotonic()
    native=UhpProcess([str(args.engine),'--feature-schema','4'])
    teacher=None;actor=None
    try:
        teacher=UhpProcess([str(args.teacher)])
        if args.source_model:actor=UhpProcess([str(args.engine),'--model',str(args.source_model)])
        while count<args.positions:
            resource_guard();storage_guard(root);rng=random.Random(args.seed+game)
            response(native,'newgame Base')
            if actor:response(actor,'newgame Base')
            rows=[];outcome=None;termination='ply_cap';game_string='Base';family=None
            for ply in range(args.cap):
                if ply%16==0:resource_guard()
                moves=response(native,'validmoves')[0].split(';')
                if ply<4:chosen=rng.choice(moves)
                else:
                    search=response(teacher,f'search {args.milliseconds} {game_string}')
                    cp=max(-6000,min(6000,int(search[0].split()[1])*4));chosen=search[1][5:]
                    row=dict(game=game,ply=ply,feature_schema=4,features=active(native),position=response(native,'nu-position')[0],
                             game_string=game_string,teacher_search_cp=cp,teacher_pv_length=int(search[2].split()[1]),
                             teacher_cp=int(response(teacher,'eval '+game_string)[0].split()[1])*4,
                             mover=1 if ply%2==0 else -1,source=config['teacher_sha256'],seed=args.seed,
                             opening_family=family,teacher_move=chosen)
                    # Search multiple legal children, then rank by their actual teacher scores.
                    if ply%4==0:
                        alternatives=rng.sample([move for move in moves if move!=chosen],min(2,len(moves)-1))
                        candidates=[]
                        for move in [chosen]+alternatives:
                            child=response(native,'play '+move)[0]
                            result=child.split(';')[1]
                            if response(native,'nu-matchdraw')[0]=='True':child_cp=0
                            elif result!='InProgress':child_cp={'WhiteWins':6000,'BlackWins':-6000,'Draw':0}[result]
                            else:child_cp=max(-6000,min(6000,int(response(teacher,f'search {args.alternative_ms} {child}')[0].split()[1])*4))
                            candidates.append(dict(move=move,cp=child_cp,features=active(native),position=response(native,'nu-position')[0]))
                            response(native,'undo')
                        candidates.sort(key=lambda c:c['cp']*row['mover'],reverse=True)
                        row['alternatives']=candidates
                        if len(candidates)>1:
                            row.update(preferred_features=candidates[0]['features'],preferred_position=candidates[0]['position'],
                                       alternative_features=candidates[-1]['features'],alternative_position=candidates[-1]['position'])
                    rows.append(row)
                    if actor and game%4==0:chosen=response(actor,'bestmove depthorseconds 64 .02')[0]
                    elif rng.random()<.08:chosen=rng.choice(moves)
                    row['played_move']=chosen
                game_string=response(native,'play '+chosen)[0]
                if actor:response(actor,'play '+chosen)
                if ply==3:family=position_key(response(native,'nu-position')[0])
                expected=response(teacher,'inspect '+game_string)[0][5:].split(';')[1]
                actual=game_string.split(';')[1]
                repeated=response(native,'nu-matchdraw')[0]=='True'
                if repeated:
                    if expected!='Draw':raise RuntimeError('teacher repetition mismatch')
                    termination='repetition';break
                if expected!=actual:
                    atomic_json(args.directory/f'failure-{game}.json',dict(game=game,ply=ply,game_string=game_string,expected=expected,actual=actual,rows=rows))
                    raise RuntimeError('unexplained teacher/core result disagreement')
                if actual!='InProgress':outcome={'WhiteWins':1,'BlackWins':-1,'Draw':0}[actual];termination='natural';break
            for row in rows:row.update(outcome=outcome,termination=termination,source_model=config['source_model_sha256'])
            atomic_json(args.directory/f'game-{game:06d}.replay.json',dict(game_string=game_string,termination=termination,outcome=outcome))
            target=args.directory/f'game-{game:06d}.jsonl';pending=target.with_suffix('.pending')
            with pending.open('w',encoding='utf8') as handle:
                for row in rows:handle.write(json.dumps(row,separators=(',',':'))+'\n')
                handle.flush()
                import os
                os.fsync(handle.fileno())
            os.replace(pending,target);count+=len(rows);game+=1
            atomic_json(manifest,dict(config=config,games=game,positions=count,completed=count>=args.positions))
            print(f'corpus games={game} positions={count}/{args.positions} termination={termination}',flush=True)
            if args.wall_seconds and time.monotonic()-started>=args.wall_seconds:break
    finally:
        native.close()
        if teacher:teacher.close()
        if actor:actor.close()
    return count>=args.positions

def active(engine):
    return [list(map(int,line.split(':')[1].split())) for line in response(engine,'nu-features')[:2]]

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--teacher',type=Path,required=True)
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--positions',type=int,default=10000)
    p.add_argument('--seed',type=int,default=99173);p.add_argument('--milliseconds',type=int,default=20)
    p.add_argument('--alternative-ms',type=int,default=5);p.add_argument('--cap',type=int,default=160)
    p.add_argument('--source-model',type=Path);p.add_argument('--wall-seconds',type=int,default=3600)
    args=p.parse_args()
    if not 1<=args.positions<=600000 or not 1<=args.milliseconds<=250 or not 1<=args.alternative_ms<=250 or not 4<=args.cap<=256:p.error('invalid bounded corpus settings')
    collect(args)

if __name__=='__main__':main()
