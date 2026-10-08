"""Pinned sequential incumbent screens, then frozen Alpha Gen 1; no promotion."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from genseki.resources import available_ram, heavy_job_path, team_job_path, job_lock
from evidence import atomic_json,digest
import arena
import research_job

def freeze(path,output):
    sha=digest(path);target=output/'artifacts'/sha/path.name
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():shutil.copyfile(path,target)
    if digest(target)!=sha:raise RuntimeError('frozen artifact mismatch')
    return target

def run(args):
    source=args.source_root
    candidates=[('incumbent-64',args.engine,source/'Alpha/work/gen2/trained/nu-64-linear.nnue'),
                ('incumbent-128',args.engine,source/'Nu/work/reliability-v8/ranking-candidate/nu-128-nonlinear.nnue'),
                ('alpha-gen1',source/'Alpha/work/gen2/gen1.exe',None)]
    if digest(candidates[-1][1])!=json.loads((source/'Alpha/reports/gen2/gen1.json').read_text())['sha256']:
        raise RuntimeError('Alpha Gen 1 pin mismatch')
    args.output.mkdir(parents=True,exist_ok=True)
    manifest_path=args.output/'series.json'
    config=dict(engine=digest(args.engine),model=digest(args.model),checkpoint=digest(args.model.with_suffix('.pt')),opponents=[dict(name=name,engine=digest(engine),model=digest(model) if model else None) for name,engine,model in candidates],
                games=20,milliseconds=250,internal_ms=230,threads=1,table_mib=16,cap=160,seed_base=82000,
                arena_sha256=digest(Path(arena.__file__)),runner_sha256=digest(Path(__file__)))
    state=json.loads(manifest_path.read_text()) if manifest_path.exists() else dict(config=config,started=time.time(),deadline=time.time()+7200,status='waiting',completed=[])
    if state['config']!=config:raise RuntimeError('series resume mismatch')
    atomic_json(manifest_path,state)
    # The primary checkout is the device-wide scheduling authority even though
    # this task's source and output live in a separate worktree.
    while True:
        if time.time()>=state['deadline']:raise RuntimeError('original series deadline expired while waiting')
        try:
            with job_lock(team_job_path(source)),job_lock(heavy_job_path(source)):
                research_job._deadline=time.monotonic()+state['deadline']-time.time()
                if available_ram()<1024**3:raise RuntimeError('RAM preflight floor')
                if shutil.disk_usage(args.output).free<512*1024**2+128*1024**2:raise RuntimeError('disk reserve')
                if os.name=='nt':
                    kernel=ctypes.windll.kernel32;kernel.GetCurrentProcess.restype=ctypes.c_void_p
                    kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
                    kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x40)
                state['status']='running';atomic_json(manifest_path,state)
                engine=freeze(args.engine,args.output);model=freeze(args.model,args.output)
                checkpoint=model.with_suffix('.pt')
                if not checkpoint.exists():shutil.copyfile(args.model.with_suffix('.pt'),checkpoint)
                if digest(checkpoint)!=config['checkpoint']:raise RuntimeError('frozen float checkpoint mismatch')
                verification=model.with_suffix('.verification.json')
                if not verification.exists():
                    import torch
                    import verify_model
                    torch.set_num_threads(1)
                    previous=sys.argv;sys.argv=['verify_model',str(model),'--engine',str(engine)]
                    try:verify_model.main()
                    finally:sys.argv=previous
                evidence=json.loads(verification.read_text())
                if not evidence['native_integer_exact'] or evidence['model_sha256']!=config['model'] or evidence['engine_sha256']!=config['engine']:
                    raise RuntimeError('integer inference verification mismatch')
                state['inference_verification']=evidence;atomic_json(manifest_path,state)
                for name,opponent,opponent_model in candidates:
                    research_job.check_deadline()
                    opponent=freeze(opponent,args.output)
                    opponent_model=freeze(opponent_model,args.output) if opponent_model else None
                    argv=['arena','--engine',str(engine),'--model',str(model),'--opponent',str(opponent),
                          '--games','20','--milliseconds','250','--threads','1','--cap','160',
                          '--seed-base','82000','--output',str(args.output/(name+'.json')),'--resume']
                    if opponent_model:argv+=['--opponent-model',str(opponent_model)]
                    print('Starting '+name,flush=True)
                    previous=sys.argv;sys.argv=argv
                    try:arena.main()
                    finally:sys.argv=previous
                    report=json.loads((args.output/(name+'.json')).read_text())
                    if not report['completed'] or report['rejected']:raise RuntimeError('invalid match: '+name)
                    if name not in state['completed']:state['completed'].append(name)
                    atomic_json(manifest_path,state)
                state.update(status='completed',finished=time.time(),production_promoted=False)
                atomic_json(manifest_path,state);return
        except PermissionError:
            if state['status']!='waiting':raise
            print('Waiting for shared heavy-job slot',flush=True);time.sleep(15)
        finally:research_job._deadline=None

def main():
    parser=argparse.ArgumentParser()
    for name in ('source-root','engine','model','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    run(args)

if __name__=='__main__':main()
