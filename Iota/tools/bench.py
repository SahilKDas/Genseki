"""Bounded end-to-end timing ladder; partial runs are never marked complete."""
import argparse
import json
import time
from common import ROOT,UhpProcess,command,atomic,digest,guard,acquire_job

def main():
    p=argparse.ArgumentParser();p.add_argument('--model',required=True);p.add_argument('--corpus',required=True)
    p.add_argument('--repeats',type=int,default=30);p.add_argument('--minutes',type=float,default=5)
    p.add_argument('--search',choices=['none','alphabeta','mcts','both'],default='none')
    p.add_argument('--milliseconds',type=int,default=250)
    p.add_argument('--threads',type=int,nargs='+',default=[1,2,4,8,12])
    p.add_argument('--output',required=True);args=p.parse_args()
    if args.repeats<1 or args.minutes<=0 or not 25<=args.milliseconds<=1000 or any(not 1<=t<=12 for t in args.threads):p.error('invalid bounded settings')
    job=acquire_job();rows=[json.loads(x) for x in open(args.corpus,encoding='utf-8')]
    games=list(dict.fromkeys(r['game'] for r in rows));positions=games[::max(1,len(games)//12)][:12]
    report=dict(model_sha256=digest(args.model),engine_sha256=digest(ROOT/'build/iota.exe'),positions=positions,samples=[],complete=False)
    engine=UhpProcess([str(ROOT/'build/iota.exe'),'--model',args.model]);deadline=time.monotonic()+args.minutes*60
    try:
        for threads in args.threads:
            command(engine,'options set Threads '+str(threads))
            for index,game in enumerate(positions):
                command(engine,'newgame '+game)
                for repeat in range(args.repeats):
                    if time.monotonic()>deadline-1:atomic(args.output,report);return
                    guard();_,elapsed=command(engine,'iota-eval',30)
                    sample=dict(threads=threads,position=index,repeat=repeat,inference_seconds=elapsed,search=[])
                    report['samples'].append(sample)
                    modes=['alphabeta','mcts'] if args.search=='both' else [] if args.search=='none' else [args.search]
                    for mode in modes:
                        if time.monotonic()>deadline-2:atomic(args.output,report);return
                        command(engine,'options set Search '+mode);legal,_=command(engine,'validmoves')
                        text=f'00:00:{args.milliseconds/1000:06.3f}'
                        response,duration=command(engine,'bestmove time '+text,3)
                        stats,_=command(engine,'iota-stats')
                        sample['search'].append(dict(mode=mode,seconds=duration,timeout=duration>args.milliseconds/1000,
                                                     legal=response[0] in legal[0].split(';'),stats=stats))
                        if not sample['search'][-1]['legal']:raise RuntimeError('illegal benchmark response')
            atomic(args.output,report)
        report['complete']=len(positions)==12;atomic(args.output,report)
    except BaseException as error:
        report['complete']=False;report['error']=repr(error);atomic(args.output,report)
        raise
    finally:engine.close()

if __name__=='__main__':main()
