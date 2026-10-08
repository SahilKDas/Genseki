"""Bounded schema-5 residual pilot; serial profiling and gated development screen.

Existing source labels and natural outcomes remain separate. No automatic promotion.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import os
import ctypes
import struct
from array import array
from train import ROOT,response,resource_guard
from evidence import atomic_json,digest
from genseki.uhp import UhpProcess
import learning
import benchmark
import arena

def invoke(module,arguments):
    previous=sys.argv
    try:sys.argv=[module.__file__]+list(map(str,arguments));module.main()
    finally:sys.argv=previous

def exposures(row):
    return [row['position']]+[row[k] for k in ('preferred_position','alternative_position') if k in row]+[c['position'] for c in row.get('alternatives',[])]

def encode(engine,row):
    def at(position):
        response(engine,'nu-loadposition '+position)
        f=[list(map(int,line.split(':')[1].split())) for line in response(engine,'nu-features')[:2]]
        return f,int(response(engine,'nu-prior')[0])
    row=dict(row);row['features'],row['prior_white']=at(row['position'])
    row.update(feature_schema=5,strategic_prior_version=1)
    if 'preferred_position' in row:
        row['preferred_features'],row['preferred_prior_white']=at(row['preferred_position'])
        row['alternative_features'],row['alternative_prior_white']=at(row['alternative_position'])
    elif 'preferred_features' in row:
        raise ValueError('ranking features require saved child positions')
    row['alternatives']=[dict(c) for c in row.get('alternatives',[])]
    for child in row['alternatives']:child['features'],child['prior_white']=at(child['position'])
    learning.validate_prior(row)
    return row

def verify_integer_inference(engine_path,model_path,rows):
    blob=model_path.read_bytes();magic,schema,count,width,scale,checksum=struct.unpack('<8sIIIIQ',blob[:32])
    if magic!=b'NUNNUE1\0' or schema!=5 or count!=8192 or scale!=256:raise ValueError('unexpected pilot model contract')
    biases=struct.unpack('<'+'i'*width,blob[32:32+4*width]);weights=array('h');weights.frombytes(blob[32+4*width:-2*width])
    output=struct.unpack('<'+'h'*width,blob[-2*width:]);verified=0
    engine=UhpProcess([str(engine_path.resolve()),'--model',str(model_path.resolve())])
    try:
        for row in rows[:24]:
            resource_guard();response(engine,'nu-loadposition '+row['position'])
            lines=response(engine,'nu-features')
            features=[list(map(int,line.split(':')[1].split())) for line in lines[:2]]
            sums=[list(biases),list(biases)]
            for p in range(2):
                for feature in features[p]:
                    for j in range(width):sums[p][j]+=weights[feature*width+j]
            side=0 if row['position'].split('|')[1]=='w' else 1
            raw=sum((min(256,max(0,sums[side][j]))-min(256,max(0,sums[1-side][j])))*output[j] for j in range(width))*600
            residual=(1 if raw>=0 else -1)*(abs(raw)//65536)
            residual=min(5000,max(-5000,residual))
            prior=int(response(engine,'nu-prior')[0])*(1 if side==0 else -1)
            expected=min(6800,max(-6800,residual+prior))
            if int(lines[2].split()[1])!=expected:raise ValueError('integer residual inference disagreement')
            verified+=1
    finally:engine.close()
    return dict(verified_positions=verified,integer_scores_equal=True,prior_version=1)

def verify_compatible_search(before,after,model,rows):
    if os.name=='nt':
        k=ctypes.windll.kernel32;k.GetCurrentProcess.restype=ctypes.c_void_p;k.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
        if not k.SetPriorityClass(k.GetCurrentProcess(),0x40):raise RuntimeError('cannot set Idle priority')
    selected=[];seen=set()
    for row in rows:
        if 4<=int(row['ply'])<=12 and row.get('game_string') and row['game_string'] not in seen:
            selected.append(row);seen.add(row['game_string'])
        if len(selected)==8:break
    results=[]
    for row in selected:
        pair=[]
        for binary in (before,after):
            engine=UhpProcess([str(binary.resolve()),'--model',str(model.resolve())])
            try:
                response(engine,'options Threads 1');response(engine,'newgame '+row['game_string'])
                lines,elapsed=engine.command('bestmove depthorseconds 2 2',2.25)
                info=response(engine,'nu-searchinfo')[0].split()
                pair.append(dict(move=lines[0],depth=int(info[1]),score=int(info[5]),nodes=int(info[3]),elapsed_ms=elapsed*1000))
            finally:engine.close()
        if any(r['depth']!=2 for r in pair) or pair[0]['score']!=pair[1]['score']:raise ValueError('schema 4 completed-depth parity failed')
        results.append(dict(ply=row['ply'],searches=pair))
    if not results:raise ValueError('no completed-depth compatibility samples')
    return dict(samples=results,all_scores_equal=True,depth=2)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--baseline-engine',type=Path,required=True)
    p.add_argument('--baseline-model',type=Path,required=True);p.add_argument('--data',type=Path,nargs='+',required=True)
    p.add_argument('--exclude-fixtures',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=int,default=1800);p.add_argument('--epochs',type=int,default=8)
    p.add_argument('--screen',action='store_true')
    args=p.parse_args()
    if not 1<=args.seconds<=7200 or not 1<=args.epochs<=100:p.error('bounded stage required')
    from research_job import check_deadline
    import research_job
    research_job._deadline=time.monotonic()+args.seconds
    files=[f for path in args.data for f in (sorted(path.glob('game-*.jsonl')) if path.is_dir() else [path])]
    identity=dict(engine=digest(args.engine),baseline=digest(args.baseline_engine),baseline_model=digest(args.baseline_model),
                  excluded=digest(args.exclude_fixtures),sources=[dict(path=f.relative_to(ROOT).as_posix() if f.is_absolute() else f.as_posix(),sha256=digest(f)) for f in files],epochs=args.epochs)
    args.output.mkdir(parents=True,exist_ok=True)
    manifest=args.output/'manifest.json';data=args.output/'corpus.jsonl'
    if manifest.exists():
        old=json.loads(manifest.read_text())
        if old['identity']!=identity or digest(data)!=old['corpus_sha256']:raise ValueError('immutable pilot identity mismatch')
    else:
        if data.exists():raise ValueError('unfinished corpus exists; preserve it and select another output')
        from position_keys import position_key
        fixture=json.loads(args.exclude_fixtures.read_text())
        reserved={key for row in fixture['records'] for key in row['exposures']}
        rows=[];excluded=0;terminal_labels=0
        engine=UhpProcess([str(args.engine.resolve()),'--feature-schema','5'])
        try:
            for file in files:
                for line in file.open(encoding='utf-8'):
                    resource_guard();row=json.loads(line)
                    if any(position_key(pos) in reserved for pos in exposures(row)):excluded+=1;continue
                    cp=row.get('teacher_search_cp',row.get('teacher_cp',row.get('search_cp')))
                    # Mate scores are never treated as nonterminal calibration targets.
                    if cp is not None and abs(cp)>=30000:terminal_labels+=1;continue
                    rows.append(encode(engine,row))
        finally:engine.close()
        if any(digest(file)!=item['sha256'] for file,item in zip(files,identity['sources'])):raise ValueError('source changed during corpus freeze')
        pending=data.with_suffix('.pending');pending.write_text(''.join(json.dumps(row)+'\n' for row in rows));pending.replace(data)
        atomic_json(manifest,dict(identity=identity,corpus_sha256=digest(data),positions=len(rows),tactical_exclusions=excluded,terminal_score_exclusions=terminal_labels,
            searched_targets='preserved teacher/search scores',outcomes='natural outcomes only; capped outcomes unused',prior_version=1))
    check_deadline()
    training=args.output/'training'
    settings=argparse.Namespace(data=[data],data_manifest=None,index=args.output/'index.sqlite',output=training,device='cpu',seed=1701,
        batch=32,accumulation=1,widths=[64],heads=['linear'],epochs=args.epochs,learning_rate=.001,ablate=None,outcome_only=False,
        initialize=None,wall_seconds=min(600,args.seconds),ranking_weight=.05,selection='mse')
    if any(digest(path)!=identity[key] for key,path in [('engine',args.engine),('baseline',args.baseline_engine),('baseline_model',args.baseline_model),('excluded',args.exclude_fixtures)]):raise ValueError('immutable artifact changed')
    if not (training/'progress.json').exists() or not json.loads((training/'progress.json').read_text()).get('completed'):
        if not learning.run(settings):return
    models=list(training.glob('*.nnue'))
    if len(models)!=1:raise ValueError('ambiguous pilot checkpoint')
    model=models[0]
    records=[json.loads(line) for line in data.open()]
    parity=args.output/'compatible-search-parity.json'
    if not parity.exists():atomic_json(parity,verify_compatible_search(args.baseline_engine,args.engine,args.baseline_model,records))
    atomic_json(args.output/'inference-parity.json',verify_integer_inference(args.engine,model,records))
    suite=args.output/'suite.json'
    if not suite.exists():
        # Deterministic development roots; never use training-validation or final seeds.
        db=learning.index_corpus([data],args.output/'index.sqlite')
        development=[json.loads(r[0]) for r in db.execute('select payload from samples where split=0 order by id')];db.close()
        choices=[r for r in development if 8<=int(r['ply'])<=32 and r.get('game_string')]
        positions=[];games=set()
        for row in choices:
            key=(row['source'],row['game'])
            if key not in games:positions.append(row['game_string']);games.add(key)
            if len(positions)==6:break
        if not positions:raise ValueError('no independent development benchmark roots')
        atomic_json(suite,dict(positions=positions,selection='first development root per source game, ply 8..32',sha256=digest(data)))
    for name,engine,weights in [('baseline',args.baseline_engine,args.baseline_model),('compatible',args.engine,args.baseline_model),('fast',args.engine,model)]:
        check_deadline();out=args.output/(name+'-threads.json')
        if not out.exists():invoke(benchmark,['--engine',engine.resolve(),'--model',weights.resolve(),'--suite',suite,'--threads',1,2,4,'--repeats',3,'--output',out])
    reports={name:json.loads((args.output/(name+'-threads.json')).read_text()) for name in ('baseline','compatible','fast')}
    if any(not r.get('completed') for r in reports.values()):raise ValueError('interrupted benchmark preserved; use new stage namespace')
    eligible=all(any(s['threads']==1 and s['timeouts']==0 for s in r['summaries']) for r in reports.values())
    verdict=dict(completed=True,production_default_changed=False,model_sha256=digest(model),preflight_passed=eligible,
        strength_claim=False,screen_requested=args.screen,screen_run=False,
        limitation='Small residual pilot; thread selection measures performance, not strength. Parallel deadline failures retained.')
    atomic_json(args.output/'verdict.json',verdict)
    if args.screen and eligible:
        check_deadline();out=args.output/'development-screen.json'
        if not out.exists() or not json.loads(out.read_text()).get('completed'):invoke(arena,['--engine',args.engine.resolve(),'--model',model.resolve(),'--opponent',args.baseline_engine.resolve(),
            '--opponent-model',args.baseline_model.resolve(),'--games',20,'--milliseconds',250,'--cap',160,'--threads',1,'--seed-base',831700,'--output',out,*(['--resume'] if out.exists() else [])])
        screened=json.loads(out.read_text())
        breakdown={kind:dict(games=sum(g['termination']==kind for g in screened['games']),points=sum(g['score'] for g in screened['games'] if g['termination']==kind)) for kind in ('natural','ply_cap','timeout')}
        verdict.update(screen_run=True,screen_completed=screened['completed'],screen_breakdown=breakdown,deadline_qualified=not any(g['termination']=='timeout' for g in screened['games']),promotion=False)
        atomic_json(args.output/'verdict.json',verdict)
    print(json.dumps(verdict))

if __name__=='__main__':
    from research_job import run
    run(main)
