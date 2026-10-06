"""Explicit bounded orchestration; never starts an unattended overnight job."""
import argparse
import json
import subprocess
import sys
import time
from common import ROOT,atomic,digest,guard

def main():
    p=argparse.ArgumentParser();p.add_argument('--minutes',type=float,required=True)
    p.add_argument('--stage',type=int,choices=[10000,50000,200000],default=10000)
    p.add_argument('--updates',type=int,default=2000)
    args=p.parse_args()
    if args.minutes<=0 or args.updates<1:p.error('positive limits required')
    deadline=time.monotonic()+args.minutes*60;corpus=ROOT/'work/corpus.jsonl'
    statepath=ROOT/'work/campaign.json';state=json.loads(statepath.read_text()) if statepath.exists() else dict(operations=[],accepted_positions=0)
    alpha=digest(ROOT.parent/'build/genseki.exe')
    if state.get('alpha_sha256',alpha)!=alpha:raise RuntimeError('frozen Alpha changed; new campaign required')
    state['alpha_sha256']=alpha;state['requested_stage']=args.stage;state['complete']=False
    def run(script,options):
        guard();remaining=(deadline-time.monotonic()-10)/60
        if remaining<=0:return False
        budget=min(10.,remaining)
        call=[sys.executable,str(ROOT/'tools'/script),*map(str,options),'--minutes',str(budget)]
        operation=dict(command=call,status='running');state['operations'].append(operation);atomic(statepath,state)
        try:result=subprocess.run(call,timeout=budget*60+15)
        except BaseException as error:
            operation['status']='failed';operation['error']=repr(error);atomic(statepath,state)
            raise
        operation['status']='finished' if result.returncode==0 else 'failed';atomic(statepath,state)
        if result.returncode:raise RuntimeError('campaign child failed')
        return True
    while time.monotonic()<deadline-10:
        positions=sum(1 for _ in corpus.open()) if corpus.exists() else 0;state['accepted_positions']=positions;atomic(statepath,state)
        if positions<args.stage:
            if not run('corpus.py',['--games',100,'--output',corpus]):break
            positions=sum(1 for _ in corpus.open()) if corpus.exists() else 0;state['accepted_positions']=positions
            # Bootstrap once a useful corpus exists, not after an entire overnight collection stage.
            if positions<256:continue
        training_complete=True
        for arch in ('cnn','gnn'):
            for width,blocks in ((32,4),(64,6)):
                for seed in (1701,1702,1703):
                    output=ROOT/f'work/v2-{arch}{width}-seed{seed}.iota';metadata=output.with_suffix('.json')
                    if metadata.exists():
                        report=json.loads(metadata.read_text())
                        if report['corpus']!=digest(corpus):
                            # Corpus changes start an explicit new experiment, never incompatible resume.
                            output=ROOT/f'work/v2-{arch}{width}-seed{seed}-n{positions}.iota';metadata=output.with_suffix('.json')
                        elif report.get('complete') and report.get('updates')==args.updates:continue
                    options=['--corpus',corpus,'--architecture',arch,'--width',width,'--blocks',blocks,
                             '--seed',seed,'--updates',args.updates,'--output',output]
                    if output.with_suffix('.pt').exists():options+=['--resume']
                    if not run('train.py',options):atomic(statepath,state);return
                    report=json.loads(output.with_suffix('.json').read_text())
                    training_complete=training_complete and report.get('complete',False) and report.get('updates')==args.updates
        if positions>=args.stage and training_complete:
            state['complete']=True;break
    state['phase']='bounded_stop' if not state['complete'] else 'training_stage_complete';atomic(statepath,state)

if __name__=='__main__':main()
