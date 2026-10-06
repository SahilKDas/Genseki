"""Matched-domain CNN controls: untied, augmented untied, and tied D6 kernels."""
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
    p.add_argument('--minutes',required=True,type=float);p.add_argument('--updates',type=int,default=2000)
    p.add_argument('--batch-size',type=int,default=128);p.add_argument('--seeds',type=int,nargs='+',default=[1701,1702,1703])
    p.add_argument('--device',choices=['cpu','cuda'],default='cuda');args=p.parse_args()
    if args.minutes<=0 or min(args.updates,args.batch_size)<1 or not args.seeds:p.error('positive bounded limits required')
    if args.output_dir.exists():raise RuntimeError('use a new experiment directory')
    args.output_dir.mkdir(parents=True);deadline=time.monotonic()+args.minutes*60
    report=dict(completed=False,corpus_sha256=digest(args.corpus),runs=[],strength_claim=False,
                controls='same hex domain, inputs, heads, optimizer updates and seeds; parameter counts differ')
    path=args.output_dir/'trial.json';experiments=[(seed,name,version,augment) for seed in args.seeds
                            for name,version,augment in [('untied',3,False),('augmented',3,True),('tied',2,False)]]
    try:
        for index,(seed,name,version,augment) in enumerate(experiments):
            guard();minutes=(deadline-time.monotonic()-10)/60/(len(experiments)-index)
            if minutes<=0:break
            output=args.output_dir/f'{name}-{seed}.iota'
            argv=[sys.executable,'-B',str(ROOT/'tools/train.py'),'--corpus',str(args.corpus),'--architecture','cnn',
                  '--width','32','--blocks','4','--version',str(version),'--updates',str(args.updates),
                  '--batch-size',str(args.batch_size),'--seed',str(seed),'--minutes',str(minutes),
                  '--device',args.device,'--output',str(output)]+(['--augment'] if augment else [])
            row=dict(name=name,seed=seed,invocation=argv,completed=False);report['runs'].append(row);atomic(path,report)
            child=subprocess.run(argv,timeout=minutes*60+20)
            if child.returncode:raise RuntimeError('CNN trial training failed')
            metadata=json.loads(output.with_suffix('.json').read_text());row['training']=metadata
            row['completed']=metadata['complete'];atomic(path,report)
            if not row['completed']:break
        report['completed']=len(report['runs'])==len(experiments) and all(r['completed'] for r in report['runs'])
    except BaseException as error:report['error']=repr(error);raise
    finally:atomic(path,report)


if __name__=='__main__':main()
