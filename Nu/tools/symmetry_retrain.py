"""Fresh schema-6 training from a hash-pinned, already curated schema-4 index."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from genseki.resources import available_ram, heavy_job_path, team_job_path, job_lock
from genseki.uhp import UhpProcess
from evidence import atomic_json, digest
import learning
import research_job
from train import response

def readonly(path):
    return sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)

def encode(row,engine):
    def features(position):
        response(engine,'nu-loadposition '+position)
        return [list(map(int,line.split(':',1)[1].split())) for line in response(engine,'nu-features')[:2]]
    row=dict(row)
    row['features']=features(row['position']);row['feature_schema']=6
    for target,position in (('preferred_features','preferred_position'),('alternative_features','alternative_position')):
        if target in row:
            if position not in row:raise RuntimeError('missing child coordinates; cannot preserve supervision')
            row[target]=features(row[position])
    if 'alternatives' in row:
        row['alternatives']=[dict(child,features=features(child['position'])) for child in row['alternatives']]
    return row

def run(args):
    import torch
    with readonly(args.source_index) as source:
        metadata=dict(source.execute('select key,value from metadata'))
        accepted=source.execute('select split,position,payload from samples order by id').fetchall()
    checkpoint=torch.load(args.checkpoint,map_location='cpu',weights_only=True)
    config=checkpoint['config']
    if config['schema']!=4 or metadata['schema']!='4' or config['corpus_id']!=metadata['identity']:
        raise RuntimeError('checkpoint does not match curated source index')
    if config['width']!=64 or config['head']!='linear':raise RuntimeError('only the authorized 64-wide linear model is enabled')
    identity=dict(source_index_sha256=digest(args.source_index),source_checkpoint_sha256=digest(args.checkpoint),
                  engine_sha256=digest(args.engine),source_config=config,
                  runtime={str(path.relative_to(ROOT)):digest(path) for path in
                           [ROOT/'Nu/tools'/name for name in ('symmetry_retrain.py','learning.py','train.py','evidence.py','research_job.py')]},
                  target_schema=6,initialization='fresh; schema-4 embedding and optimizer are not reused')
    args.output.mkdir(parents=True,exist_ok=True)
    state_path=args.output/'stage.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else dict(identity=identity,started=time.time(),deadline=time.time()+args.seconds,status='running')
    if state['identity']!=identity:raise RuntimeError('stage resume identity mismatch')
    remaining=state['deadline']-time.time()
    if remaining<=0:raise RuntimeError('original stage deadline expired')
    research_job._deadline=time.monotonic()+remaining
    atomic_json(state_path,state)
    corpus=args.output/'schema6.jsonl';schema_index=args.output/'schema6.sqlite'
    try:
        if available_ram()<2*1024**3:raise RuntimeError('RAM below 2 GiB preflight reserve')
        if shutil.disk_usage(args.output).free<512*1024**2+128*1024**2:raise RuntimeError('disk reserve')
        if not torch.cuda.is_available():raise RuntimeError('CUDA unavailable; GPU training required')
        if not corpus.exists():
            engine=UhpProcess([str(args.engine),'--feature-schema','6'])
            pending=corpus.with_suffix('.pending')
            try:
                if response(engine,'nu-feature-schema')!=['6']:raise RuntimeError('schema-6 encoder unavailable')
                with pending.open('w',encoding='utf8') as output:
                    for number,(_,_,payload) in enumerate(accepted):
                        research_job.check_deadline()
                        output.write(json.dumps(encode(json.loads(payload),engine),separators=(',',':'))+'\n')
                        if (number+1)%64==0:print(f'reencoded {number+1}/{len(accepted)}',flush=True)
                    output.flush();os.fsync(output.fileno())
                os.replace(pending,corpus)
            finally:engine.close()
        sha=digest(corpus)
        if state.get('corpus_sha256',sha)!=sha:raise RuntimeError('reencoded corpus changed')
        state['corpus_sha256']=sha
        atomic_json(state_path,state)
        db=learning.index_corpus([corpus],schema_index)
        try:
            actual=dict(db.execute('select position,split from samples'))
            if actual!={position:split for split,position,_ in accepted}:raise RuntimeError('curated samples/splits changed')
            splits=[db.execute('select count(*) from samples where split=?',(split,)).fetchone()[0] for split in (0,1)]
        finally:db.close()
        state.update(status='training',positions=len(accepted),splits=splits,curation_metadata=metadata)
        atomic_json(state_path,state)
        settings=SimpleNamespace(data_manifest=None,data=[corpus],index=schema_index,output=args.output/'models',
            widths=[64],heads=['linear'],epochs=config['epochs'],batch=config['batch'],accumulation=config['accumulation'],
            seed=config['seed'],learning_rate=config['learning_rate'],ranking_weight=config.get('ranking_weight',.05),
            selection=config.get('selection','mse'),device='cuda',ablate=config.get('ablate'),outcome_only=False,
            initialize=None,wall_seconds=max(1,int(state['deadline']-time.time())-5))
        complete=learning.run(settings)
        state.update(status='trained' if complete else 'paused',finished=time.time(),production_promoted=False)
        if complete:
            model=settings.output/'nu-64-linear.nnue'
            state.update(model_sha256=digest(model),model=str(model.relative_to(args.output)))
        if digest(args.source_index)!=identity['source_index_sha256'] or digest(args.checkpoint)!=identity['source_checkpoint_sha256']:
            raise RuntimeError('source artifacts changed during training')
        atomic_json(state_path,state)
    except BaseException as error:
        state.update(status='failed',error=repr(error),finished=time.time())
        atomic_json(state_path,state);raise
    finally:research_job._deadline=None

def main():
    parser=argparse.ArgumentParser()
    for name in ('source-root','source-index','checkpoint','engine','output'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--seconds',type=int,default=7200)
    args=parser.parse_args()
    if not 1<=args.seconds<=7200:parser.error('stage must be bounded to two hours')
    with job_lock(team_job_path(args.source_root)),job_lock(heavy_job_path(args.source_root)):
        if os.name=='nt':
            kernel=ctypes.windll.kernel32
            kernel.GetCurrentProcess.restype=ctypes.c_void_p
            kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
            kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x40)
        run(args)

if __name__=='__main__':main()
