"""User-authorized research-incumbent registration, with schema-collision parity."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import struct
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from genseki.resources import job_lock,team_job_path,heavy_job_path,available_ram
from genseki.uhp import UhpProcess
from evidence import atomic_json,digest

def command(engine,text):
    lines,_=engine.command(text,10)
    if any(line.startswith(('err ','invalidmove ')) for line in lines):raise RuntimeError(lines)
    return lines

def promote(args):
    import torch
    torch.set_num_threads(1)
    if available_ram()<1024**3:raise RuntimeError('RAM preflight floor')
    original=ROOT/'Nu/work/symmetry-v5/linear-64'
    source_model=original/'models/nu-64-linear.nnue'
    series=original.parent/'gauntlets/series-001'
    series_state=json.loads((series/'series.json').read_text())
    if series_state['status']!='completed':raise RuntimeError('development series incomplete')
    if digest(source_model)!=series_state['config']['model']:raise RuntimeError('model does not match completed gauntlets')
    old_engine=series/'artifacts'/series_state['config']['engine']/'nu.exe'
    if digest(old_engine)!=series_state['config']['engine']:raise RuntimeError('original engine pin mismatch')
    raw=source_model.read_bytes()
    if raw[:8]!=b'NUNNUE1\0' or struct.unpack_from('<III',raw,8)!=(5,8192,64):raise RuntimeError('unexpected migration source')
    migrated=bytearray(raw);struct.pack_into('<I',migrated,8,6)
    assert bytes(migrated[32:])==raw[32:]
    # A new directory preserves both the original model and all frozen evidence.
    import hashlib
    model_sha=hashlib.sha256(migrated).hexdigest()
    engine_sha=digest(args.engine)
    destination=args.source_root/'Nu/work/incumbents/64-linear'/model_sha/engine_sha
    destination.mkdir(parents=True,exist_ok=True)
    model=destination/'nu-64-linear.nnue';engine=destination/'nu.exe'
    if model.exists():
        if digest(model)!=model_sha:raise RuntimeError('incumbent model changed')
    else:
        with model.open('xb') as output:output.write(migrated)
    if not engine.exists():shutil.copyfile(args.engine,engine)
    if digest(engine)!=engine_sha:raise RuntimeError('incumbent engine changed')
    checkpoint=model.with_suffix('.pt')
    saved=torch.load(source_model.with_suffix('.pt'),map_location='cpu',weights_only=True)
    if saved['config']['schema']!=5:raise RuntimeError('unexpected float checkpoint schema')
    saved['config']=dict(saved['config'],schema=6)
    saved['migration']=dict(source_checkpoint_sha256=digest(source_model.with_suffix('.pt')),source_schema=5,
                           target_schema=6,weights_unchanged=True,optimizer_resume_authorized=False)
    if not checkpoint.exists():
        pending=checkpoint.with_suffix('.pending');torch.save(saved,pending);os.replace(pending,checkpoint)
    migrated_checkpoint=torch.load(checkpoint,map_location='cpu',weights_only=True)
    if migrated_checkpoint['config']!=saved['config']:raise RuntimeError('checkpoint configuration mismatch')
    for name,tensor in saved['state'].items():
        if not torch.equal(tensor,migrated_checkpoint['state'][name]):raise RuntimeError('checkpoint weights changed')
    rows=[json.loads(line) for line in (original/'schema5.jsonl').read_text().splitlines()]
    old=UhpProcess([str(old_engine),'--model',str(source_model)])
    try:
        new=UhpProcess([str(engine),'--model',str(model)])
        try:
            if command(new,'nu-feature-schema')[0]!='6':raise RuntimeError('schema-6 loader failed')
            for row in rows:
                for peer in (old,new):command(peer,'nu-loadposition '+row['position'])
                if command(old,'nu-features')!=command(new,'nu-features'):raise RuntimeError('feature/inference parity failed')
            for index in range(0,len(rows),32):
                for peer in (old,new):command(peer,'nu-loadposition '+rows[index]['position'])
                moves=[command(peer,'bestmove depth 1')[0] for peer in (old,new)]
                infos=[command(peer,'nu-searchinfo') for peer in (old,new)]
                if moves[0]!=moves[1] or infos[0]!=infos[1]:raise RuntimeError('fixed-depth search parity failed')
        finally:new.close()
    finally:old.close()
    evidence=dict(schema_migration='canonical-D6-mobility-v1: header 5 -> 6 only',
                  source_model_sha256=digest(source_model),model_sha256=model_sha,engine_sha256=engine_sha,
                  payload_unchanged=True,feature_score_parity_positions=len(rows),fixed_depth_parity_positions=len(range(0,len(rows),32)))
    atomic_json(destination/'migration.json',evidence)
    previous=args.source_root/'Alpha/work/gen2/trained/nu-64-linear.nnue'
    record=dict(role='64-wide-research-incumbent',status='user-promoted',production_default_changed=False,
                architecture=dict(width=64,head='linear'),schema=6,feature_contract='nu-canonical-d6-mobility-v1',
                required_pair=dict(engine=str(engine.relative_to(args.source_root).as_posix()),engine_sha256=engine_sha,
                                   model=str(model.relative_to(args.source_root).as_posix()),model_sha256=model_sha),
                checkpoint=str(checkpoint.relative_to(args.source_root).as_posix()),checkpoint_sha256=digest(checkpoint),
                predecessor_model_sha256=digest(previous),promotion_authority='explicit user request',
                sealed_qualification=False,evidence=evidence,
                development_results=[dict(opponent=name,points=json.loads((series/(name+'.json')).read_text())['points'],games=20,
                                         evidence_sha256=digest(series/(name+'.json'))) for name in ('incumbent-64','incumbent-128','alpha-gen1')])
    atomic_json(args.source_root/'Nu/incumbents/64-linear.json',record)
    print(json.dumps(record,indent=2))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--source-root',type=Path,required=True);parser.add_argument('--engine',type=Path,required=True)
    args=parser.parse_args()
    with job_lock(team_job_path(args.source_root)),job_lock(heavy_job_path(args.source_root)):
        if os.name=='nt':
            kernel=ctypes.windll.kernel32;kernel.GetCurrentProcess.restype=ctypes.c_void_p
            kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
            kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x40)
        promote(args)

if __name__=='__main__':main()
