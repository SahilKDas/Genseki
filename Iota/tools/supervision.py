"""Bounded search-distribution and partial-alternative targets from a frozen Iota teacher."""
import argparse
import json
import time
from pathlib import Path
from common import ROOT,UhpProcess,command,atomic,digest,guard,acquire_job
from learning import Corpus


def search_target(engine,milliseconds):
    command(engine,f'bestmove time 00:00:00.{milliseconds+20:03d}',3)
    lines,_=command(engine,'iota-searchinfo')
    header=lines[0].split();nodes=int(header[1]);score=float(header[5])/1000
    policy=list(map(float,lines[1:]))
    if nodes<2 or not policy or abs(sum(policy)-1)>1e-4 or not -1<=score<=1:
        raise ValueError('incomplete or invalid teacher search')
    return policy,score,nodes


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--corpus',required=True,type=Path);p.add_argument('--model',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path);p.add_argument('--minutes',type=float,required=True)
    p.add_argument('--positions',type=int,default=1000);p.add_argument('--search-ms',type=int,default=250)
    p.add_argument('--alternatives',type=int,default=8)
    args=p.parse_args()
    if not 1<=args.positions<=200000 or not 25<=args.search_ms<=500 or not 0<=args.alternatives<=8 or args.minutes<=0:p.error('invalid bounded settings')
    if args.output.exists():raise RuntimeError('choose a new corpus output; never overwrite evidence')
    job=acquire_job();corpus=Corpus(args.corpus)
    identity=digest(args.model);engine_hash=digest(ROOT/'build/iota.exe');input_hash=digest(args.corpus)
    report=dict(teacher_sha256=identity,engine_sha256=engine_hash,input_sha256=input_hash,accepted=0,
                rejected=[],completed=False,label_kind='MCTS root visits; partial child-search ranking; exact one-reply tactics')
    args.output.parent.mkdir(parents=True,exist_ok=True);deadline=time.monotonic()+args.minutes*60
    engine=UhpProcess([str(ROOT/'build/iota.exe'),'--model',str(args.model)])
    temporary=args.output.with_suffix('.pending')
    try:
        command(engine,'options set Search mcts');command(engine,'options set Threads 1')
        queues={name:iter(offsets) for name,offsets in corpus.splits.items()};remaining=set(queues)
        def positions():
            # Preserve held-out coverage even when a bounded collector stops early.
            order=['train']*8+['validation','test']
            while remaining:
                for split in order:
                    if split not in remaining:continue
                    try:yield corpus.row(next(queues[split]))
                    except StopIteration:remaining.remove(split)
        with temporary.open('w',encoding='utf-8') as target:
            for number,row in enumerate(positions()):
                if report['accepted']>=args.positions or time.monotonic()>=deadline-3:break
                guard();command(engine,'newgame '+row['game'])
                try:
                    legal,_=command(engine,'validmoves');moves=legal[0].split(';')
                    policy,score,nodes=search_target(engine,args.search_ms)
                    if len(policy)!=len(moves):raise ValueError('teacher policy/legal list mismatch')
                    tactics,_=command(engine,'iota-tactics 500',2)
                    labels=[list(map(int,t.split()[1:])) for t in tactics]
                    if len(labels)!=len(moves):raise ValueError('incomplete tactical labels')
                    selected=sorted(range(len(moves)),key=lambda i:(-policy[i],i))[:1]
                    if args.alternatives:
                        for k in range(args.alternatives):
                            i=k*(len(moves)-1)//max(1,args.alternatives-1)
                            if i not in selected:selected.append(i)
                    else:selected=[]
                    alternatives=[]
                    for index in selected[:args.alternatives]:
                        if time.monotonic()>=deadline-3:raise TimeoutError('collection budget exhausted')
                        child,_=command(engine,'play '+moves[index]);result=child[0].split(';')[1]
                        try:
                            if result in ('WhiteWins','BlackWins','Draw'):
                                own=row['game'].split(';')[2].startswith('White')
                                value=0. if result=='Draw' else (1. if (result=='WhiteWins')==own else -1.)
                            else:_,child_value,_=search_target(engine,args.search_ms);value=-child_value
                            alternatives.append([index,value])
                        finally:command(engine,'undo')
                    enriched=dict(row,policy=policy,search_value=score,alternatives=alternatives,tactics=labels,
                                  search_teacher_sha256=identity,search_nodes=nodes,search_ms=args.search_ms,
                                  label_kind=report['label_kind'],ranking_complete=len(alternatives)==len(moves))
                    target.write(json.dumps(enriched)+'\n');target.flush();report['accepted']+=1
                except (RuntimeError,ValueError,TimeoutError) as error:
                    report['rejected'].append(dict(row=number,error=repr(error)))
                atomic(args.output.with_suffix('.manifest.json'),report)
        temporary.replace(args.output)
        if digest(args.model)!=identity or digest(ROOT/'build/iota.exe')!=engine_hash or digest(args.corpus)!=input_hash:raise RuntimeError('teacher/corpus changed during collection')
        report.update(completed=report['accepted']==args.positions,corpus_sha256=digest(args.output))
        atomic(args.output.with_suffix('.manifest.json'),report)
    except BaseException as error:
        report['error']=repr(error);atomic(args.output.with_suffix('.manifest.json'),report);raise
    finally:engine.close()


if __name__=='__main__':main()
