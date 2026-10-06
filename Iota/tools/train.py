from __future__ import annotations
import argparse
import json
import random
import time
import shutil
from pathlib import Path
import numpy as np
import torch
from models import Network, parse_encoding
from learning import Corpus, supervised_loss, distillation_loss
from common import ROOT, UhpProcess, command, atomic, digest, guard, acquire_job

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--corpus', required=True)
    p.add_argument('--architecture', choices=['cnn','gnn'], required=True)
    p.add_argument('--width', type=int, choices=[32,64], default=32)
    p.add_argument('--blocks', type=int, choices=[4,6], default=4)
    p.add_argument('--version', type=int, choices=[1,2,3], default=2)
    p.add_argument('--teacher-checkpoint', type=Path)
    p.add_argument('--distillation-weight',type=float,default=1.)
    p.add_argument('--temperature',type=float,default=2.)
    p.add_argument('--ranking-weight',type=float,default=.25)
    p.add_argument('--tactical-weight',type=float,default=.5)
    p.add_argument('--augment',action='store_true')
    p.add_argument('--updates', type=int, default=2000)
    p.add_argument('--batch-size', type=int, default=128)
    p.add_argument('--seed', type=int, default=1701)
    p.add_argument('--minutes', type=float, default=30)
    p.add_argument('--resume', action='store_true')
    p.add_argument('--device', choices=['cpu','cuda'], default='cuda')
    p.add_argument('--output', required=True)
    args=p.parse_args()
    if args.version==3 and args.architecture!='cnn':p.error('version 3 is the untied CNN control')
    if args.updates < 1 or args.batch_size < 1 or args.minutes <= 0 or not all(np.isfinite(x) and x>=0 for x in (args.distillation_weight,args.ranking_weight,args.tactical_weight)) or not np.isfinite(args.temperature) or args.temperature<=0: p.error('invalid bounded learning settings')
    job=acquire_job(); torch.set_num_threads(1)
    random.seed(args.seed); np.random.seed(args.seed); torch.manual_seed(args.seed)
    if args.device=='cuda':
        if not torch.cuda.is_available(): raise RuntimeError('CUDA requested but unavailable')
        torch.cuda.set_per_process_memory_fraction(min(1.,1.5*1024**3/torch.cuda.get_device_properties(0).total_memory))
    identity=digest(args.corpus)
    corpus=Corpus(args.corpus);train=corpus.splits['train'];val=corpus.splits['validation']
    if not train or not val: raise RuntimeError('independent training and validation games required')
    net=Network(args.architecture,args.width,args.blocks,args.version).to(args.device)
    teacher=None;teacher_hash=None;teacher_value_mode='none'
    if args.teacher_checkpoint:
        teacher_hash=digest(args.teacher_checkpoint)
        state=torch.load(args.teacher_checkpoint,map_location='cpu',weights_only=False)
        cfg=state['config'];teacher=Network(cfg['architecture'],cfg['width'],cfg['blocks'],cfg.get('version',1)).to(args.device)
        teacher.load_state_dict(state['model']);teacher.eval();teacher.requires_grad_(False)
        labels=state.get('supervision',{})
        teacher_value_mode='wdl' if labels.get('wdl',0) else 'score' if labels.get('search_value',0) else 'none'
    optimizer=torch.optim.AdamW(net.parameters(), lr=.001, weight_decay=.0001)
    out=Path(args.output); out.parent.mkdir(parents=True,exist_ok=True)
    statepath=out.with_suffix('.pt'); update=0; history=[]
    config={k:getattr(args,k) for k in ('architecture','width','blocks','version','batch_size','seed','distillation_weight','temperature','ranking_weight','tactical_weight','augment')}
    config['teacher_sha256']=teacher_hash
    config['teacher_value_mode']=teacher_value_mode
    sources={str(path.relative_to(ROOT)):digest(path) for directory in ('src','tools') for path in (ROOT/directory).glob('*') if path.is_file()}
    if args.resume:
        state=torch.load(statepath,map_location='cpu',weights_only=False)
        old_config=dict(state['config'])
        for key,default in dict(version=1,distillation_weight=1.,temperature=2.,ranking_weight=.25,tactical_weight=.5,augment=False,teacher_sha256=None,teacher_value_mode='none').items():old_config.setdefault(key,default)
        if state['corpus']!=identity or old_config!=config: raise RuntimeError('resume identity mismatch')
        net.load_state_dict(state['model']);optimizer.load_state_dict(state['optimizer'])
        for values in optimizer.state.values():
            for k,v in values.items():
                if isinstance(v,torch.Tensor): values[k]=v.to(args.device)
        random.setstate(state['random']);np.random.set_state(state['numpy']);torch.set_rng_state(state['torch'])
        if args.device=='cuda' and state['cuda'] is not None: torch.cuda.set_rng_state_all(state['cuda'])
        update=state['update'];history=state['history']
    engine=UhpProcess([str(ROOT/'build/iota.exe')]); deadline=time.monotonic()+args.minutes*60
    def sample(row,network):
        command(engine,'newgame '+row['game'])
        lines,_=command(engine,'iota-encode '+network.architecture+(str(network.version) if network.version>=2 else ''))
        return parse_encoding(lines,args.device)
    def loss(offset,training=False):
        row=corpus.row(offset)
        if training and args.augment:
            command(engine,'newgame '+row['game']);position,_=command(engine,'iota-position')
            from symmetry import transform_position,action_permutation,remap_targets
            before,_=command(engine,'iota-actions');rotation=random.randrange(6);reflection=bool(random.randrange(2))
            transformed=transform_position(position[0],rotation,reflection)
            command(engine,'iota-loadposition '+transformed);after,_=command(engine,'iota-actions')
            row=remap_targets(row,action_permutation(before,after,rotation,reflection));row['position']=transformed
        def encoded(network):
            if 'position' not in row:return sample(row,network)
            command(engine,'iota-loadposition '+row['position'])
            lines,_=command(engine,'iota-encode '+network.architecture+(str(network.version) if network.version>=2 else ''))
            return parse_encoding(lines,args.device)
        prediction=net(*encoded(net))
        total=supervised_loss(*prediction,row,args.ranking_weight,args.tactical_weight)
        if teacher is not None:
            with torch.no_grad():reference=teacher(*encoded(teacher))
            total+=args.distillation_weight*distillation_loss(prediction,reference,args.temperature,teacher_value_mode)
        return total
    def save():
        if digest(args.corpus)!=identity or (args.teacher_checkpoint and digest(args.teacher_checkpoint)!=teacher_hash):
            raise RuntimeError('training input changed during run')
        temp=statepath.with_suffix('.tmp')
        torch.save(dict(model=net.state_dict(),optimizer=optimizer.state_dict(),corpus=identity,
                        config=config,update=update,history=history,random=random.getstate(),
                        supervision=corpus.supervision,
                        numpy=np.random.get_state(),torch=torch.get_rng_state(),
                        cuda=torch.cuda.get_rng_state_all() if args.device=='cuda' else None),temp)
        temp.replace(statepath); modelhash=net.export(out)
        atomic(out.with_suffix('.json'),dict(config=config,corpus=identity,updates=update,history=history,
               model_sha256=modelhash,complete=update==args.updates,device=args.device,
               parameters=sum(p.numel() for p in net.parameters()),source_sha256=sources,
               supervision=corpus.supervision,
               engine_sha256=digest(ROOT/'build/iota.exe'),torch_version=torch.__version__,
               peak_gpu_allocated=torch.cuda.max_memory_allocated() if args.device=='cuda' else 0))
    try:
        while update<args.updates and time.monotonic()<deadline-5:
            guard();net.train();optimizer.zero_grad();total=0
            # Stream one position at a time; effective batch never controls a giant allocation.
            for _ in range(args.batch_size):
                if time.monotonic()>=deadline-5: optimizer.zero_grad();save();return
                pool=corpus.tactical if corpus.tactical and random.random()<.25 else train
                value=loss(random.choice(pool),True);total+=float(value.detach());(value/args.batch_size).backward()
            optimizer.step();update+=1
            if update%25==0 or update==args.updates:
                net.eval()
                with torch.no_grad(): validation=float(np.mean([float(loss(r)) for r in val[:32]]))
                previous=min((h['validation'] for h in history),default=float('inf'))
                history.append(dict(update=update,loss=total/args.batch_size,validation=validation));save()
                if validation<previous:
                    net.export(out.with_suffix('.best.iota'));shutil.copyfile(statepath,out.with_suffix('.best.pt'))
                print(history[-1],flush=True)
        save()
    except BaseException as error:
        optimizer.zero_grad()
        save()
        report=json.loads(out.with_suffix('.json').read_text())
        report['complete']=False;report['error']=repr(error);atomic(out.with_suffix('.json'),report)
        raise
    finally: engine.close()

if __name__=='__main__': main()
