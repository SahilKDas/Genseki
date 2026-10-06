"""Bounded, leakage-controlled NNUE training with resumable optimizer checkpoints."""
import argparse
from array import array
import hashlib
import json
import math
import os
from pathlib import Path
import random
import sqlite3
import time
from evidence import atomic_json, digest
from train import export, pooled_transform, resource_guard

GROUPS = {'identity': (0,2048), 'type': (2048,4096), 'occupancy': (4096,6144),
          'pinning': (6144,6400), 'gates': (6400,6800), 'queen': (6800,7000),
          'mobility': (7000,7400), 'stack': (7400,7600)}

def position_key(position):
    fields=position.split('|')
    if len(fields)!=6 or fields[0]!='G1':raise ValueError('expected canonical G1 position')
    # Post-opening legality no longer depends on absolute ply counters.
    key='|'.join((fields[1],str(min(int(fields[3]),4)),str(min(int(fields[4]),4)),fields[5]))
    return hashlib.sha256(key.encode()).hexdigest()

def index_corpus(paths, output):
    """Discard every transposition crossing a held-out opening/game group."""
    identities=[dict(path=str(path.resolve()),sha256=digest(path)) for path in paths]
    signature=hashlib.sha256(json.dumps(identities,sort_keys=True).encode()).hexdigest()
    if output.exists():
        connection=sqlite3.connect(output)
        if connection.execute('select value from metadata where key="identity"').fetchone()[0]!=signature:
            connection.close();raise RuntimeError('corpus index identity mismatch; use a new index')
        return connection
    pending=output.with_name(output.name+'.pending')
    if pending.exists():raise RuntimeError('unfinished index exists; preserve it and choose a new output')
    output.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(pending)
    db.execute('pragma cache_size=-8192')
    db.execute('create table metadata(key text primary key,value text)')
    db.execute('create table samples(id integer primary key, split integer, position text, game text, natural integer, payload text)')
    db.execute('create table exposures(sample integer,position text,split integer)')
    families={}
    try:
        # Game boundaries remain intact even when old data lacks an opening-family field.
        for path in paths:
            with path.open(encoding='utf8') as handle:
                for line in handle:
                    row=json.loads(line);game=f"{row['source']}:{row.get('seed',0)}:{row['game']}"
                    if row.get('opening_family') is not None:families[game]=str(row['opening_family'])
                    elif int(row['ply'])==4:families[game]=position_key(row['position'])
        schemas=set();seen=0
        for path in paths:
            with path.open(encoding='utf8') as handle:
                for line in handle:
                    row=json.loads(line);schemas.add(row.get('feature_schema',1))
                    if len(schemas)!=1 or not schemas.issubset({1,2,3,4}):raise RuntimeError('mixed/unsupported feature schemas')
                    game=f"{row['source']}:{row.get('seed',0)}:{row['game']}"
                    family=families.get(game,game)
                    split=int(hashlib.sha256(family.encode()).hexdigest()[:8],16)%5==0
                    natural=row.get('termination')=='natural' and row.get('outcome') is not None
                    inserted=db.execute('insert into samples(split,position,game,natural,payload) values(?,?,?,?,?)',
                               (int(split),position_key(row['position']),game,int(natural),line.strip()))
                    positions=[row['position']]+[row[k] for k in ('preferred_position','alternative_position') if k in row]
                    positions += [candidate['position'] for candidate in row.get('alternatives',[])]
                    for position in set(positions):db.execute('insert into exposures values(?,?,?)',(inserted.lastrowid,position_key(position),int(split)))
                    seen+=1
                    if seen%2000==0:resource_guard();db.commit()
        db.execute('create index sample_positions on samples(position,split)')
        db.execute('create index exposure_positions on exposures(position,split)')
        db.execute('delete from samples where id in (select sample from exposures where position in (select position from exposures group by position having min(split)!=max(split)))')
        # Equivalent records cannot gain disproportionate weight through repeated loops.
        db.execute('delete from samples where id not in (select min(id) from samples group by position)')
        db.execute('create index sample_split on samples(split,id)')
        db.execute('insert into metadata values("identity",?)',(signature,))
        db.execute('insert into metadata values("schema",?)',(str(next(iter(schemas))),))
        db.execute('insert into metadata values("input_records",?)',(str(seen),))
        db.commit();db.close();os.replace(pending,output)
    except BaseException:
        db.close();raise
    return sqlite3.connect(output)

def make_network(width, head, schema):
    import torch
    from torch import nn
    class Network(nn.Module):
        def __init__(self):
            super().__init__();self.width=width;self.schema=schema
            self.embedding=nn.Embedding(8192,width)
            nn.init.uniform_(self.embedding.weight,-.03,.03)
            self.bias=nn.Parameter(torch.zeros(width))
            self.head=nn.Linear(2*width,32) if head=='nonlinear' else None
            self.output=nn.Parameter(torch.empty(32 if self.head else width).uniform_(-.12,.12))
        def forward(self, ids, offsets):
            value=pooled_transform(ids,offsets,self.embedding.weight,self.width,self.bias).clamp(0,1)
            if self.head is None:return ((value[:,0]-value[:,1])*self.output).sum(1)
            own=self.head(value.flatten(1)).clamp(0,1)
            enemy=self.head(value.flip(1).flatten(1)).clamp(0,1)
            return ((own-enemy)*self.output).sum(1)*.5
    return Network()

def atomic_checkpoint(path, value):
    import torch
    temporary=path.with_name(path.name+'.pending');torch.save(value,temporary);os.replace(temporary,path)

def cpu_tree(value):
    import torch
    if isinstance(value,torch.Tensor):return value.detach().cpu().clone()
    if isinstance(value,dict):return {k:cpu_tree(v) for k,v in value.items()}
    if isinstance(value,list):return [cpu_tree(v) for v in value]
    if isinstance(value,tuple):return tuple(cpu_tree(v) for v in value)
    return value

def run(args):
    import torch
    torch.set_num_threads(4)
    if args.data_manifest:args.data=[Path(path) for path in json.loads(args.data_manifest.read_text())]
    if not args.data:raise RuntimeError('need corpus files or a frozen corpus manifest')
    args.data=[file for path in args.data for file in (sorted(path.glob('game-*.jsonl')) if path.is_dir() else [path])]
    resource_guard()
    device=torch.device('cuda' if args.device=='auto' and torch.cuda.is_available() else 'cpu' if args.device=='auto' else args.device)
    if device.type=='cuda':
        device=torch.device('cuda',device.index or 0)
        total=torch.cuda.get_device_properties(device).total_memory
        torch.cuda.set_per_process_memory_fraction(min(1,1.5*1024**3/total),device)
    db=index_corpus(args.data,args.index);db.execute('pragma cache_size=-8192')
    schema=int(db.execute('select value from metadata where key="schema"').fetchone()[0])
    corpus_id=db.execute('select value from metadata where key="identity"').fetchone()[0]
    train_ids=array('I',(r[0] for r in db.execute('select id from samples where split=0 order by id')))
    valid_ids=array('I',(r[0] for r in db.execute('select id from samples where split=1 order by id')))
    if not train_ids or not valid_ids:raise RuntimeError('need disjoint nonempty training/validation groups')
    natural=[db.execute('select count(distinct game) from samples where split=? and natural=1',(split,)).fetchone()[0] for split in (0,1)]
    if args.outcome_only and (natural[0]<500 or natural[1]<100):raise RuntimeError('outcome fine-tuning needs 500/100 natural games')
    if args.ablate and schema!=4:raise RuntimeError('feature ablations require schema 4')
    excluded=GROUPS.get(args.ablate,(-1,-1))
    def rows(ids):
        values={}
        for start in range(0,len(ids),900):
            chunk=ids[start:start+900];marks=','.join('?' for _ in chunk)
            values.update(db.execute(f'select id,payload from samples where id in ({marks})',tuple(map(int,chunk))))
        return [json.loads(values[int(i)]) for i in ids]
    def tensors(batch, field='features'):
        ids=[];offsets=[0];targets=[];eligible=[]
        for row in batch:
            for features in row[field]:
                ids.extend(i for i in features if not excluded[0]<=i<excluded[1]);offsets.append(len(ids))
            cp=row.get('teacher_search_cp',row.get('teacher_cp',row.get('search_cp',0)))
            outcome=row.get('outcome') if row.get('termination')=='natural' else None
            targets.append(outcome if args.outcome_only and outcome is not None else
                           math.tanh(cp/600) if outcome is None else .9*math.tanh(cp/600)+.1*outcome)
            eligible.append(outcome is not None if args.outcome_only else
                            any(k in row for k in ('teacher_search_cp','teacher_cp','search_cp')))
        return (torch.tensor(ids,dtype=torch.long,device=device),torch.tensor(offsets,dtype=torch.long,device=device),
                torch.tensor(targets,dtype=torch.float32,device=device),torch.tensor(eligible,device=device))
    args.output.mkdir(parents=True,exist_ok=True);reports=[];started=time.monotonic()
    for width in args.widths:
        for head in args.heads:
            torch.manual_seed(args.seed)
            if device.type=='cuda':torch.cuda.reset_peak_memory_stats(device)
            net=make_network(width,head,schema).to(device)
            if args.ablate:
                with torch.no_grad():net.embedding.weight[excluded[0]:excluded[1]].zero_()
            optimizer=torch.optim.AdamW(net.parameters(),lr=args.learning_rate)
            name=f'nu-{width}-{head}'+(f'-without-{args.ablate}' if args.ablate else '')
            checkpoint=args.output/(name+'.resume.pt')
            config=dict(corpus_id=corpus_id,width=width,head=head,schema=schema,seed=args.seed,batch=args.batch,
                        accumulation=args.accumulation,epochs=args.epochs,learning_rate=args.learning_rate,
                        ablate=args.ablate,outcome_only=args.outcome_only,
                        initialize_sha256=digest(args.initialize) if args.initialize else None)
            epoch=cursor=updates=0;best_loss=float('inf');best_state=None;best_optimizer=None;selected=0
            if checkpoint.exists():
                saved=torch.load(checkpoint,map_location='cpu',weights_only=True)
                if saved['config']!=config:raise RuntimeError('resume configuration mismatch')
                net.load_state_dict(saved['state']);optimizer.load_state_dict(saved['optimizer'])
                epoch=saved['epoch'];cursor=saved['cursor'];updates=saved['updates']
                best_loss=saved['best_loss'];best_state=saved['best_state'];best_optimizer=saved['best_optimizer'];selected=saved['selected']
                torch.set_rng_state(saved['torch_rng'])
                if device.type=='cuda' and saved['cuda_rng'] is not None:torch.cuda.set_rng_state(saved['cuda_rng'],device)
            elif args.initialize:
                initial=torch.load(args.initialize,map_location='cpu',weights_only=True)
                if initial['config']['width']!=width or initial['config']['head']!=head or initial['config']['schema']!=schema:
                    raise RuntimeError('fine-tuning architecture/schema mismatch')
                net.load_state_dict(initial['state'])
            elif args.outcome_only:raise RuntimeError('outcome fine-tuning requires a trained initialization')
            def save():
                atomic_checkpoint(checkpoint,dict(config=config,state=cpu_tree(net.state_dict()),optimizer=cpu_tree(optimizer.state_dict()),
                    epoch=epoch,cursor=cursor,updates=updates,best_loss=best_loss,best_state=best_state,best_optimizer=best_optimizer,
                    selected=selected,torch_rng=torch.get_rng_state(),cuda_rng=torch.cuda.get_rng_state(device) if device.type=='cuda' else None))
            while epoch<args.epochs:
                resource_guard();order=array('I',train_ids);random.Random(args.seed+epoch).shuffle(order)
                while cursor<len(order):
                    end=min(len(order),cursor+args.batch*args.accumulation)
                    batch=rows(order[cursor:end]);optimizer.zero_grad(set_to_none=True)
                    for start in range(0,len(batch),args.batch):
                        micro=batch[start:start+args.batch];ids,offsets,target,eligible=tensors(micro)
                        errors=torch.nn.functional.smooth_l1_loss(net(ids,offsets).tanh(),target,reduction='none')
                        loss=(errors*eligible).sum()/max(1,len(batch))
                        preferences=[]
                        for row in micro:
                            candidates=row.get('alternatives',[])
                            if len(candidates)>1:
                                for alternative in candidates[1:]:
                                    if candidates[0]['cp']*row['mover']<=alternative['cp']*row['mover']:continue
                                    preferences.append(dict(row,preferred_features=candidates[0]['features'],alternative_features=alternative['features']))
                            elif 'preferred_features' in row:preferences.append(row)
                        if preferences:
                            px,po,_,_=tensors(preferences,'preferred_features');ax,ao,_,_=tensors(preferences,'alternative_features')
                            signs=torch.tensor([r['mover'] for r in preferences],device=device)
                            loss+=.05*torch.nn.functional.softplus(-signs*(net(px,po)-net(ax,ao))/.25).sum()/len(batch)
                        if not torch.isfinite(loss):raise RuntimeError('nonfinite training loss; last checkpoint preserved')
                        loss.backward()
                    torch.nn.utils.clip_grad_norm_(net.parameters(),1.0,error_if_nonfinite=True);optimizer.step();updates+=1;cursor=end
                    if updates%32==0:resource_guard();save()
                    if args.wall_seconds and time.monotonic()-started>=args.wall_seconds:
                        save();atomic_json(args.output/'progress.json',dict(completed=False,model=name,epoch=epoch,cursor=cursor,updates=updates));db.close();return False
                with torch.no_grad():
                    total=count=0
                    for start in range(0,len(valid_ids),args.batch):
                        ids,offsets,target,eligible=tensors(rows(valid_ids[start:start+args.batch]))
                        total+=(((net(ids,offsets).tanh()-target).square())*eligible).sum().item();count+=eligible.sum().item()
                if not count:raise RuntimeError('no eligible held-out targets')
                if total/count<best_loss:
                    best_loss=total/count;best_state=cpu_tree(net.state_dict());best_optimizer=cpu_tree(optimizer.state_dict());selected=epoch+1
                epoch+=1;cursor=0;save()
                print(f'{name} epoch={epoch}/{args.epochs} updates={updates} validation_mse={total/count:.6f}',flush=True)
            net.load_state_dict(best_state);path=args.output/(name+'.nnue');export(net,path)
            atomic_checkpoint(path.with_suffix('.pt'),dict(state=best_state,optimizer=best_optimizer,config=config,selected_epoch=selected))
            report=dict(**config,updates=updates,completed=True,validation_mse=best_loss,selected_epoch=selected,
                        train_positions=len(train_ids),validation_positions=len(valid_ids),natural_games=natural,
                        sha256=digest(path),peak_cuda_bytes=torch.cuda.max_memory_allocated(device) if device.type=='cuda' else 0)
            atomic_json(args.output/(name+'.json'),report);reports.append(report)
            del net,optimizer,best_optimizer,best_state
            if device.type=='cuda':torch.cuda.empty_cache()
    atomic_json(args.output/'training.json',reports);atomic_json(args.output/'progress.json',dict(completed=True));db.close();return True

def main():
    p=argparse.ArgumentParser()
    inputs=p.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--data',type=Path,nargs='+');inputs.add_argument('--data-manifest',type=Path)
    p.add_argument('--index',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--epochs',type=int,default=24)
    p.add_argument('--batch',type=int,default=128);p.add_argument('--accumulation',type=int,default=1)
    p.add_argument('--widths',type=int,nargs='+',choices=(64,128),default=[64,128])
    p.add_argument('--heads',nargs='+',choices=('linear','nonlinear'),default=['linear','nonlinear'])
    p.add_argument('--device',default='auto');p.add_argument('--seed',type=int,default=1701)
    p.add_argument('--learning-rate',type=float,default=.001);p.add_argument('--wall-seconds',type=int,default=0)
    p.add_argument('--ablate',choices=tuple(GROUPS));p.add_argument('--outcome-only',action='store_true')
    p.add_argument('--initialize',type=Path)
    args=p.parse_args()
    if not 1<=args.batch<=512 or not 1<=args.accumulation<=16 or not 1<=args.epochs<=100 or args.wall_seconds<0 or not 0<args.learning_rate<=.01:p.error('invalid bounded training settings')
    run(args)

if __name__=='__main__':main()
