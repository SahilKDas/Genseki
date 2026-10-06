"""Held-out partial-action ranking audit; never a playing-strength claim."""
import argparse
import json
import sqlite3
import time
from pathlib import Path
from learning import make_network,decision_metrics
from train import resource_guard
from evidence import atomic_json,digest
from genseki.uhp import UhpProcess
from train import response

def main():
    import torch
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--index',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=int,default=120)
    p.add_argument('--engine',type=Path);p.add_argument('--model',type=Path);args=p.parse_args()
    if bool(args.engine)!=bool(args.model):p.error('native audit requires both engine and model')
    if not 1<=args.seconds<=300:p.error('bounded seconds required')
    resource_guard();torch.set_num_threads(1)
    checkpoint=torch.load(args.checkpoint,map_location='cpu',weights_only=True);config=checkpoint['config']
    net=make_network(config['width'],config['head'],config['schema']);net.load_state_dict(checkpoint['state']);net.eval()
    db=sqlite3.connect(f'{args.index.resolve().as_uri()}?mode=ro',uri=True)
    identity=db.execute('select value from metadata where key="identity"').fetchone()[0]
    if config['corpus_id']!=identity:raise RuntimeError('held-out corpus identity mismatch')
    deadline=time.monotonic()+args.seconds;records=[];predictions=[];complete=True
    native=UhpProcess([str(args.engine),'--model',str(args.model)]) if args.engine else None
    try:
        with torch.no_grad():
            for payload, in db.execute('select payload from samples where split=1 order by id'):
                if time.monotonic()>=deadline:complete=False;break
                row=json.loads(payload);children=row.get('alternatives',[])
                if len(children)<2:continue
                resource_guard();ids=[];offsets=[0]
                for child in children:
                    for side in child['features']:ids.extend(side);offsets.append(len(ids))
                if native:
                    values=[]
                    for child in children:
                        response(native,'nu-loadposition '+child['position'])
                        value=int(response(native,'nu-features')[2].split()[1])
                        values.append(value*(1 if child['position'].split('|')[1]=='w' else -1))
                else:values=net(torch.tensor(ids,dtype=torch.long),torch.tensor(offsets,dtype=torch.long)).tolist()
                records.append(row);predictions.append(values)
        atomic_json(args.output,dict(checkpoint_sha256=digest(args.checkpoint),corpus_id=identity,
                   complete=complete,partial_action_lists=True,inference='native' if native else 'float',
                   model_sha256=digest(args.model) if args.model else None,
                   engine_sha256=digest(args.engine) if args.engine else None,**decision_metrics(records,predictions)))
    finally:
        db.close()
        if native:native.close()

if __name__=='__main__':main()
