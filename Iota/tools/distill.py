"""Explicit, bounded large-teacher -> search labels -> small-student -> search benchmark."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from common import ROOT,atomic,digest,guard


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--corpus',required=True,type=Path);p.add_argument('--output-dir',required=True,type=Path)
    p.add_argument('--minutes',required=True,type=float)
    p.add_argument('--teacher-updates',type=int,default=2000);p.add_argument('--student-updates',type=int,default=2000)
    p.add_argument('--batch-size',type=int,default=128);p.add_argument('--seed',type=int,default=1701)
    p.add_argument('--student-architecture',choices=['cnn','gnn'],default='gnn')
    p.add_argument('--device',choices=['cuda','cpu'],default='cuda')
    p.add_argument('--search-positions',type=int,default=1000)
    args=p.parse_args()
    if args.minutes<=0 or min(args.teacher_updates,args.student_updates,args.batch_size)<1 or not 0<=args.search_positions<=200000:p.error('invalid bounded campaign settings')
    if args.output_dir.exists():raise RuntimeError('choose a new experiment directory')
    args.output_dir.mkdir(parents=True);deadline=time.monotonic()+args.minutes*60
    report=dict(completed=False,corpus_sha256=digest(args.corpus),phases=[],strength_claim=False,
                engine_sha256=digest(ROOT/'build/iota.exe'),seed=args.seed)
    state=args.output_dir/'campaign.json'
    def run(script,options,fraction=1.):
        guard();remaining=(deadline-time.monotonic()-10)/60
        if remaining<=0:return False
        budget=remaining*fraction
        argv=[sys.executable,'-B',str(ROOT/'tools'/script),*map(str,options),'--minutes',str(budget)]
        phase=dict(script=script,invocation=argv,completed=False);report['phases'].append(phase);atomic(state,report)
        try:
            result=subprocess.run(argv,timeout=budget*60+20)
            if result.returncode:raise RuntimeError(f'{script} failed with {result.returncode}')
            phase['completed']=True;atomic(state,report);return True
        except BaseException as error:
            phase['error']=repr(error);atomic(state,report);raise
    common=['--corpus',args.corpus,'--batch-size',args.batch_size,'--seed',args.seed,'--version',2,'--device',args.device,'--augment']
    teacher=args.output_dir/'teacher.iota';student=args.output_dir/'student.iota'
    try:
        if not run('train.py',[*common,'--architecture','gnn','--width',64,'--blocks',6,'--updates',args.teacher_updates,'--output',teacher],.45):return
        if not json.loads(teacher.with_suffix('.json').read_text())['complete']:return
        checkpoint=teacher.with_suffix('.best.pt');report['teacher_sha256']=digest(checkpoint)
        corpus=args.corpus
        if args.search_positions:
            corpus=args.output_dir/'search-corpus.jsonl'
            if not run('supervision.py',['--corpus',args.corpus,'--model',teacher.with_suffix('.best.iota'),'--output',corpus,'--positions',args.search_positions],.25):return
            if not json.loads(corpus.with_suffix('.manifest.json').read_text())['completed']:return
            common[1]=corpus
        if not run('train.py',[*common,'--architecture',args.student_architecture,'--width',32,'--blocks',4,'--updates',args.student_updates,'--teacher-checkpoint',checkpoint,'--output',student],.65):return
        if not json.loads(student.with_suffix('.json').read_text())['complete']:return
        for label,model in (('teacher',teacher),('student',student)):
            output=args.output_dir/f'{label}-search-bench.json'
            if not run('bench.py',['--model',model.with_suffix('.best.iota'),'--corpus',corpus,'--search','both','--threads',1,'--repeats',3,'--output',output],.5 if label=='teacher' else 1.):return
            if not json.loads(output.read_text())['complete']:return
        report['completed']=True
        report['student_sha256']=digest(student.with_suffix('.best.iota'))
    finally:
        report['elapsed_seconds']=args.minutes*60-max(0,deadline-time.monotonic());atomic(state,report)


if __name__=='__main__':main()
