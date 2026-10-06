"""Isolated, hash-pinned Gen 2 development stages. Never promotes production."""
import argparse
import contextlib
import hashlib
import json
import math
import os
from pathlib import Path
import random
import shutil
import struct
import subprocess
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from genseki.uhp import UhpProcess
WORK=ROOT/'Alpha/work/gen2'
REPORT=ROOT/'Alpha/reports/gen2'
ENGINE=ROOT/'Alpha/build/gen2-target/release/alpha_nokamute_mit.exe'
NU=ROOT/'build-nu/nu.exe'

def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def freeze_search():
    sha=digest(ENGINE);target=WORK/'search'/sha/ENGINE.name
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():shutil.copyfile(ENGINE,target)
    if digest(target)!=sha:raise RuntimeError('frozen search mismatch')
    pin=REPORT/'search-pins'/(sha+'.json')
    if pin.exists():return
    sources=[p for folder in ('Alpha/vendor/nokamute/src','Alpha/vendor/minimax-rs/src') for p in (ROOT/folder).rglob('*.rs')]
    atomic(pin,dict(sha256=sha,binary=str(target.relative_to(ROOT)),source_sha256={str(p.relative_to(ROOT)):digest(p) for p in sources}))
def atomic(p,v):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    pending=p.with_name(p.name+'.pending')
    with pending.open('w',encoding='utf8') as f:json.dump(v,f,indent=2,allow_nan=False);f.flush();os.fsync(f.fileno())
    os.replace(pending,p)
def read(p):return json.loads(Path(p).read_text())
def training_runtime():
    pin=REPORT/'trainer-latest-pin.json'
    files=['Nu/tools/'+name for name in ('learning.py','train.py','evidence.py','decisions.py')]
    identities={file:digest(ROOT/file) for file in files}
    revision=hashlib.sha256(json.dumps(identities,sort_keys=True).encode()).hexdigest()
    if pin.exists() and read(pin)['files']!=identities:
        raise RuntimeError('latest Nu changed after pinning; use a new training campaign')
    if not pin.exists():
        root=WORK/'trainer'/revision;root.mkdir(parents=True,exist_ok=True)
        for file in files:
            target=root/file;target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/file,target)
            if digest(target)!=identities[file]:raise RuntimeError('Nu changed during runtime snapshot')
        atomic(pin,dict(revision=revision,source='latest Nu working tree',root=str(root.relative_to(ROOT)),files=identities))
    metadata=read(pin);root=ROOT/metadata['root']
    for file,sha in metadata['files'].items():
        if not (root/file).exists():
            if digest(ROOT/file)!=sha:raise RuntimeError('pinned trainer unavailable and current source differs')
            (root/file).parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(ROOT/file,root/file)
        if digest(root/file)!=sha:raise RuntimeError('pinned trainer changed')
    return root/'Nu/tools'
def pin_latest_nu():
    training_runtime()
    source=ROOT/'Nu/work/reliability-v8/ranking-candidate/nu-128-nonlinear.nnue'
    metadata=source.with_suffix('.json');evidence=read(metadata)
    if evidence.get('selected_updates',0)<=0:raise RuntimeError('latest Nu artifact is untrained')
    sha=digest(source);target=WORK/'nu-latest'/sha/source.name
    if evidence.get('model_sha256')!=sha:raise RuntimeError('latest Nu training provenance checksum mismatch')
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and digest(target)!=sha:raise RuntimeError('latest Nu snapshot changed')
    if not target.exists():shutil.copyfile(source,target)
    sidecar=Path(str(target)+'.alpha.json')
    if not sidecar.exists():atomic(sidecar,dict(trained=True,sha256=sha,score_scale=.25,source=str(source.relative_to(ROOT)),training_sha256=digest(metadata),qualified=False))
    atomic(REPORT/'nu-latest.json',dict(model=str(target.relative_to(ROOT)),sha256=sha,source=str(source.relative_to(ROOT)),training_sha256=digest(metadata),trainer=read(REPORT/'trainer-latest-pin.json'),qualified=False))
    return target

def stage_start(path,config,seconds,now=None):
    now=time.time() if now is None else now
    progress=read(path) if Path(path).exists() else dict(config=config,started=now,deadline=now+seconds,status='running')
    if progress['config']!=config:raise RuntimeError('stage resume mismatch')
    if now>=progress['deadline']:raise RuntimeError('original stage deadline expired; start a separately named stage')
    atomic(path,progress)
    return progress,min(seconds,max(1,int(progress['deadline']-now)))
def cmd(e,text,timeout=5):
    lines,elapsed=e.command(text,timeout)
    if any(x.startswith(('err ','invalidmove ')) for x in lines):raise RuntimeError(lines)
    return lines[:-1],elapsed
@contextlib.contextmanager
def engine(path,args=()):
    e=UhpProcess([str(path),*map(str,args)])
    try:yield e
    finally:e.close()
def features(e,command):
    lines,_=cmd(e,command)
    return [list(map(int,x.split(':',1)[1].split())) for x in lines[:2]],lines
def floors():
    from genseki.rho.core import available_ram
    if available_ram()<2*1024**3:raise RuntimeError('RAM below 2 GiB; resumable stop')
    if shutil.disk_usage(ROOT).free<512*1024**2:raise RuntimeError('disk reserve')
def heavy_conflict():
    if os.name!='nt':return False
    output=subprocess.check_output(['powershell','-NoProfile','-Command',"@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python' } | Select-Object ProcessId,CommandLine) | ConvertTo-Json -Compress"],text=True)
    processes=json.loads(output or '[]');processes=processes if isinstance(processes,list) else [processes]
    for process in processes:
        line=(process.get('CommandLine') or '').replace('\\','/').lower()
        if process['ProcessId']!=os.getpid() and any(pattern in line for pattern in ('campaign','gauntlet','genseki.arena','gen2.py arena','gen2.py train','gen2.py collect','gen2.py benchmark','gen2_lab.py','learning.py','train.py','arena.py','benchmark.py','tournament','selfplay','training.py')):return True
    return False
def guard():
    floors()
    # Enumerate only explicitly named temporary roots; never enter Iota.
    paths=[ROOT/'.tmp',ROOT/'build',ROOT/'build-nu',ROOT/'Alpha/build',ROOT/'Alpha/work',ROOT/'Nu/work',ROOT/'Rho']
    sizes=[sum(p.stat().st_size for p in root.rglob('*') if p.is_file()) if root.exists() else 0 for root in paths]
    if sum(sizes)>10_000_000_000 or sum(sizes[4:])>6_000_000_000:raise RuntimeError('device storage cap')
def settings(e,threads=1):
    for name,value in [('NumThreads',threads),('BackgroundPondering','False'),('RandomOpening','False'),('TableSizeMiB',32)]:cmd(e,f'options set {name} {value}')
def neural(e,path):cmd(e,f'options set ModelPath {path}');cmd(e,'options set Evaluator neural')
def tactical_keys(position_key):
    positions=[f'G1|w|{turns*2}|{turns}|{turns}|0,-1=bQ;0,0=wQ,bB1' for turns in (2,3,4)]
    positions.extend(f'G1|b|7|4|{turns}|-1,0=wA1;-1,1=bA2;0,-1=bQ;0,0=wQ;0,1=wS2;1,-1=wS1;1,0=bA1' for turns in (3,4))
    with engine(ROOT/'build/genseki_rules.exe') as e:
        for fixture in read(ROOT/'Alpha/reports/profile-suite.json')['records']:
            game=fixture['position']
            if game.split(';')[0]!='Base':continue
            cmd(e,'newgame Base')
            for move in game.split(';')[3:]:
                if move:cmd(e,'play '+move)
            positions.append(cmd(e,'genseki-position')[0][0])
    return sorted({position_key(position) for position in positions})
def curated_index(learning,files,index,checkpoint):
    db=learning.index_corpus(files,index);keys=tactical_keys(learning.position_key)
    signature=hashlib.sha256(json.dumps(keys).encode()).hexdigest()
    previous=db.execute('select value from metadata where key="tactical_exclusions"').fetchone()
    marks=','.join('?' for _ in keys)
    excluded=f'select sample from exposures where position in ({marks})'
    count=db.execute(f'select count(*) from samples where id in ({excluded})',keys).fetchone()[0]
    if (previous and previous[0]!=signature) or (count and checkpoint.exists()):
        db.close();raise RuntimeError('held-out registry changed; preserve checkpoints and use a new corpus namespace')
    db.execute(f'delete from samples where id in ({excluded})',keys)
    db.execute('insert or replace into metadata values("tactical_exclusions",?)',(signature,));db.commit()
    return db,signature,count

def prepare():
    WORK.mkdir(parents=True,exist_ok=True);REPORT.mkdir(parents=True,exist_ok=True)
    freeze=REPORT/'gen1.json'
    binary=WORK/'gen1.exe'
    if not binary.exists():shutil.copyfile(ROOT/'build/genseki.exe',binary)
    identity=dict(label='Alpha Gen 1',sha256=digest(binary),source_revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),production_default_unchanged=True)
    if freeze.exists() and read(freeze)['sha256']!=identity['sha256']:raise RuntimeError('Gen 1 snapshot changed')
    if not freeze.exists():atomic(freeze,identity)
    artifacts={digest(p):p for p in (ROOT/'Nu/work').rglob('*.nnue')}
    choices=[]
    reports=list((ROOT/'Nu/work').glob('*development*.json'))+list((ROOT/'Nu/work/campaign-v6').glob('*development*.json'))
    for report in reports:
        data=read(report);games=data.get('games',[]);path=artifacts.get(data.get('model_sha256'))
        if not path or len(games)<20:continue
        if any(g.get('termination') in ('timeout','illegal','divergence','protocol_error') for g in games):continue
        choices.append((sum(g['score'] for g in games)/len(games),str(path),report))
    if not choices:raise RuntimeError('no eligible trained development model')
    score,path,report=max(choices)
    path=Path(path);sha=digest(path)
    training=path.parent/'training.json'
    evidence=read(training) if training.exists() else read(path.with_suffix('.json'))
    rows=evidence if isinstance(evidence,list) else [evidence]
    if not any(r.get('updates',0)>0 and (r.get('sha256',sha)==sha) for r in rows):raise RuntimeError('trained provenance unavailable')
    target=WORK/'nu-baseline.nnue'
    if target.exists() and digest(target)!=sha:raise RuntimeError('baseline is immutable; use a new campaign')
    if not target.exists():shutil.copyfile(path,target)
    sidecar=Path(str(target)+'.alpha.json')
    if not sidecar.exists():atomic(sidecar,dict(trained=True,sha256=sha,score_scale=.25,source=str(path.relative_to(ROOT)),training_sha256=digest(training) if training.exists() else digest(path.with_suffix('.json'))))
    atomic(REPORT/'nu-baseline.json',dict(model_sha256=sha,source=str(path.relative_to(ROOT)),development_report=str(report.relative_to(ROOT)),development_report_sha256=digest(report),development_score=score,qualified=False))
    print(json.dumps(read(REPORT/'nu-baseline.json'),indent=2))

def parity(args):
    rng=random.Random(220601);checks=0;stacks=undos=0
    model=Path(args.model or WORK/'nu-baseline.nnue').resolve()
    start=time.monotonic();nu_hash=digest(NU)
    nu_sources={str(p.relative_to(ROOT)):digest(p) for p in sorted((ROOT/'Nu/src').glob('*')) if p.is_file()}
    nu_sources['Nu/CMakeLists.txt']=digest(ROOT/'Nu/CMakeLists.txt')
    with engine(ENGINE) as a,engine(NU,['--model',model]) as n:
        settings(a);neural(a,model)
        for game in range(args.games):
            cmd(a,'newgame Base');cmd(n,'newgame Base')
            for ply in range(160):
                if time.monotonic()-start>=args.seconds:raise RuntimeError('parity deadline; no complete validation claim')
                # Nu's diagnostic prints active IDs before evaluate() refreshes them.
                cmd(n,'nu-features')
                fa,la=features(a,'alpha-neural');fn,ln=features(n,'nu-features')
                if fa!=fn:atomic(REPORT/'parity-failure.json',dict(game=game,ply=ply,alpha=fa,nu=fn));raise RuntimeError('feature divergence')
                raw=int(la[2].split()[1]);score=int(ln[2].split()[1])
                if raw!=score:raise RuntimeError(f'integer inference divergence {raw} != {score}')
                cmd(a,'alpha-eval');checks+=1
                ma=cmd(a,'validmoves')[0][0].split(';');mn=cmd(n,'validmoves')[0][0].split(';')
                if {cmd(n,'nu-moveid '+m)[0][0] for m in ma}!={cmd(n,'nu-moveid '+m)[0][0] for m in mn}:raise RuntimeError('legal-move divergence')
                move=rng.choice(sorted(ma));ga=cmd(a,'play '+move)[0][0];gn=cmd(n,'play '+move)[0][0]
                if ga.split(';')[1]!=gn.split(';')[1]:raise RuntimeError('result divergence')
                if ply%7==0:
                    cmd(a,'undo');cmd(n,'undo');cmd(n,'nu-features');fa,_=features(a,'alpha-neural');fn,_=features(n,'nu-features');assert fa==fn;undos+=1
                    cmd(a,'play '+move);cmd(n,'play '+move)
                if ga.split(';')[1] not in ('InProgress','NotStarted'):break
        cmd(a,'options set Evaluator gen1');cmd(a,'newgame Base+MLP')
        before=cmd(a,'options get Evaluator')[0]
        response,_=a.command('options set Evaluator neural');assert any(x.startswith('err ') for x in response)
        assert cmd(a,'options get Evaluator')[0]==before
    if digest(NU)!=nu_hash:raise RuntimeError('Nu reference binary changed during parity')
    if any(digest(ROOT/p)!=sha for p,sha in nu_sources.items()):raise RuntimeError('Nu reference source changed during parity')
    result=dict(checks=checks,undos=undos,seconds=time.monotonic()-start,features_exact=True,integer_inference_exact=True,model_sha256=digest(model),engine_sha256=digest(ENGINE),nu_engine_sha256=nu_hash,nu_sources=nu_sources)
    atomic(REPORT/(model.stem+'-parity.json'),result);print(result)

def schemas(args):
    guard()
    deadline=time.monotonic()+args.seconds;verified=[]
    sources=sorted((ROOT/'Nu/work/campaign-v6/models').glob('*.nnue'))
    for source in sources:
        if time.monotonic()>=deadline:raise RuntimeError('schema verification deadline')
        evidence=read(source.parent/'training.json');sha=digest(source)
        if not any(row.get('sha256')==sha and row.get('updates',0)>0 for row in evidence):raise RuntimeError('missing trained model provenance')
        target=WORK/'verification'/(source.parent.name+'-'+source.name)
        target.parent.mkdir(exist_ok=True)
        if target.exists() and digest(target)!=sha:raise RuntimeError('verification artifact changed')
        if not target.exists():shutil.copyfile(source,target)
        atomic(str(target)+'.alpha.json',dict(trained=True,sha256=sha,score_scale=.25,source=str(source.relative_to(ROOT)),training_sha256=digest(source.parent/'training.json'),verification_only=True))
        parity(SimpleNamespace(model=str(target),games=2,seconds=max(1,int(deadline-time.monotonic()))))
        verified.append(read(REPORT/(target.stem+'-parity.json')))
    atomic(REPORT/'schemas.json',dict(artifacts=verified,all_exact=True))

def collect(args):
    guard();root=WORK/args.corpus;root.mkdir(exist_ok=True)
    manifest=root/'manifest.json'
    teacher_hash=read(manifest)['config']['teacher_sha256'] if manifest.exists() else digest(ENGINE)
    teacher_binary=WORK/'teachers'/teacher_hash/ENGINE.name
    teacher_binary.parent.mkdir(parents=True,exist_ok=True)
    if not teacher_binary.exists():
        if digest(ENGINE)!=teacher_hash:raise RuntimeError('original teacher binary unavailable; preserve corpus and use a new namespace')
        shutil.copyfile(ENGINE,teacher_binary)
    if digest(teacher_binary)!=teacher_hash:raise RuntimeError('teacher snapshot mismatch')
    identity=dict(teacher_sha256=digest(teacher_binary),gen1_sha256=read(REPORT/'gen1.json')['sha256'],model_sha256=digest(WORK/'nu-baseline.nnue'),seed=220610,depth=4,teacher_ms=250,cap=160)
    if manifest.exists() and read(manifest)['config']!=identity:raise RuntimeError('corpus resume mismatch')
    files=sorted(root.glob('game-*.jsonl'));game=len(files);started=time.monotonic();end=started+args.seconds
    with engine(teacher_binary) as teacher,engine(teacher_binary) as neural_engine,engine(ROOT/'build/genseki_rules.exe') as rules:
        settings(teacher);settings(neural_engine);neural(neural_engine,WORK/'nu-baseline.nnue')
        while game<args.games and time.monotonic()<end:
            guard();rng=random.Random(identity['seed']+game);rows=[];outcome=None;termination='ply_cap';family=None
            for e in (teacher,neural_engine,rules):cmd(e,'newgame Base')
            for ply in range(160):
                if time.monotonic()>=end:break
                floors()
                f,diag=features(neural_engine,'alpha-neural');position=cmd(rules,'genseki-position')[0][0]
                if ply==4:family=hashlib.sha256(position.encode()).hexdigest()
                legal=cmd(teacher,'validmoves')[0][0].split(';')
                response_lines=cmd(teacher,'alpha-search 4 250',3)[0]
                response=response_lines[0]
                parts=response.split(' move ',1);score=int(parts[0].split()[1]);static=int(parts[0].split()[3]);chosen=parts[1]
                current=cmd(rules,'newgame '+('Base' if not rows else rows[-1]['next_game']))[0][0]
                mover=1 if ply%2==0 else -1
                # Nu trainer consumes white-oriented scores in Nu units.
                rows.append(dict(source=identity['teacher_sha256'],seed=identity['seed']+game,game=game,ply=ply,features=f,feature_schema=struct.unpack_from('<I',(WORK/'nu-baseline.nnue').read_bytes(),8)[0],neural_raw=int(diag[2].split()[1]),teacher_search_cp=score*mover*4,teacher_static_cp=static*mover*4,mover=mover,position=position,game_string=current,opening_family=family,teacher_depth_limit=4,search_diagnostics=response_lines[1:]))
                move=rng.choice(sorted(legal)) if ply<4 or rng.random()<.1 else chosen
                results=[cmd(e,'play '+move)[0][0] for e in (teacher,neural_engine,rules)]
                states=[g.split(';')[1] for g in results]
                if states==['Draw','Draw','InProgress']:
                    after=cmd(rules,'genseki-position')[0][0]
                    key=lambda s:(s.split('|')[1],s.split('|')[-1])
                    occurrences=sum(key(row['position'])==key(after) for row in rows)+1
                    if occurrences>=3:
                        termination='repetition_adjudication';rows[-1]['next_game']=results[-1];break
                if len(set(states))!=1:atomic(root/f'failure-{game}.json',dict(results=results,rows=rows));raise RuntimeError('rules divergence')
                rows[-1]['next_game']=results[-1]
                if states[0] not in ('InProgress','NotStarted'):outcome={'WhiteWins':1,'BlackWins':-1,'Draw':0}[states[0]];termination='natural';break
            if time.monotonic()>=end:break  # Discard incomplete game; replay committed games only.
            for row in rows:row.update(outcome=outcome,termination=termination,opening_family=family or f'opening-{game}')
            p=root/f'game-{game:06d}.jsonl';tmp=p.with_suffix('.pending')
            with tmp.open('w') as f:
                for row in rows:f.write(json.dumps(row)+'\n')
                f.flush();os.fsync(f.fileno())
            os.replace(tmp,p);game+=1
            atomic(manifest,dict(config=identity,games=game,positions=sum(sum(1 for _ in p.open()) for p in root.glob('game-*.jsonl')),complete=game>=args.games))
            print('corpus games',game,flush=True)

def rule_aware_predictions(rows,predictions):
    if len(rows)!=len(predictions):raise ValueError('decision count mismatch')
    result=[]
    for row,values in zip(rows,predictions):
        children=row.get('alternatives',[])
        if len(children)!=len(values):raise ValueError('child prediction count mismatch')
        adjusted=[]
        for child,value in zip(children,values):
            if not math.isfinite(float(value)):raise ValueError('nonfinite decision prediction')
            if child.get('repetition_draw'):adjusted.append(0.)
            elif child.get('terminal') is not None:
                if child['terminal'] not in (-1,0,1):raise ValueError('invalid terminal outcome')
                adjusted.append(child['terminal']*10.)
            else:adjusted.append(max(-5000/600,min(5000/600,float(value))))
        result.append(adjusted)
    return result

def train(args):
    deadline=time.monotonic()+args.seconds
    guard();sys.path.insert(0,str(training_runtime()))
    import learning
    files=sorted((WORK/args.corpus).glob('game-*.jsonl'))
    if not files:raise RuntimeError('collect a corpus first')
    project=WORK if args.corpus=='corpus' else WORK/'runs'/args.corpus
    project.mkdir(parents=True,exist_ok=True)
    runtime_pin=project/'training-runtime.json'
    identity=read(REPORT/'trainer-latest-pin.json')
    identity=identity|dict(alpha_wrapper_sha256=digest(__file__))
    if runtime_pin.exists() and read(runtime_pin)!=identity:raise RuntimeError('trainer resume identity mismatch; use a new corpus namespace')
    if not runtime_pin.exists():
        if (project/'trained/nu-64-linear.resume.pt').exists():raise RuntimeError('legacy checkpoint retained; latest Nu requires a new corpus namespace')
        atomic(runtime_pin,identity)
    options=SimpleNamespace(data=files,data_manifest=None,index=project/'training-index.sqlite',output=project/'trained',epochs=12,batch=128,accumulation=1,widths=[64],heads=['linear'],device='auto',seed=220620,learning_rate=.001,wall_seconds=args.seconds,ablate=None,outcome_only=False,initialize=None)
    options.selection=getattr(args,'selection','regret');options.ranking_weight=getattr(args,'ranking_weight',.25)
    db,exclusion_signature,excluded=curated_index(learning,files,options.index,options.output/'nu-64-linear.resume.pt')
    if options.selection=='regret':
        counts=[sum(bool(json.loads(row[0]).get('full_width')) and len(json.loads(row[0]).get('alternatives',[]))>=2 for row in db.execute('select payload from samples where split=?',(split,))) for split in (0,1)]
        if not all(counts):db.close();raise RuntimeError('regret selection requires full-width decisions in disjoint training and validation families')
    db.close()
    options.wall_seconds=int(deadline-time.monotonic())-2
    if options.wall_seconds<=0:return
    original_metrics=learning.decision_metrics
    learning.decision_metrics=lambda rows,values:original_metrics(rows,rule_aware_predictions(rows,values))
    try:completed=learning.run(options)
    finally:learning.decision_metrics=original_metrics
    if not completed:return
    path=options.output/'nu-64-linear.nnue';meta=read(path.with_suffix('.json'))
    if meta['updates']<=0:raise RuntimeError('untrained artifact')
    sidecar=Path(str(path)+'.alpha.json')
    if sidecar.exists() and read(sidecar)['sha256']!=digest(path):raise RuntimeError('trained candidate changed; use a new corpus namespace')
    if not sidecar.exists():atomic(sidecar,dict(trained=True,sha256=digest(path),score_scale=.25,training=meta,teacher=read(WORK/args.corpus/'manifest.json')['config']))
    targets={'search_score_positions':0,'natural_outcome_positions':0,'adjudicated_positions':0}
    for file in files:
        for line in file.open():
            row=json.loads(line);targets['search_score_positions']+=1
            targets['natural_outcome_positions' if row['termination']=='natural' else 'adjudicated_positions']+=1
    atomic(REPORT/('training.json' if args.corpus=='corpus' else 'training-'+args.corpus+'.json'),meta|dict(target_sources=targets,tactical_exclusion_signature=exclusion_signature,excluded_tactical_positions=excluded,production_promoted=False))

def calibrate(args):
    guard()
    deadline=time.monotonic()+args.seconds
    model=Path(args.model or WORK/'nu-baseline.nnue').resolve()
    sidecar=Path(str(model)+'.alpha.json');manifest=read(sidecar)
    if any(read(p).get('config',{}).get('model_sha256')==digest(model) and read(p).get('games') for p in REPORT.glob('*.json')):raise RuntimeError('cannot calibrate after matches; freeze first')
    numerator=denominator=target_squared=0.;count=0
    sys.path.insert(0,str(training_runtime()));import learning
    files=sorted((WORK/args.corpus).glob('game-*.jsonl'))
    if not files:raise RuntimeError('collect a corpus before calibration')
    project=WORK if args.corpus=='corpus' else WORK/'runs'/args.corpus
    project.mkdir(parents=True,exist_ok=True)
    db,exclusion_signature,_=curated_index(learning,files,project/'training-index.sqlite',project/'trained/nu-64-linear.resume.pt')
    with engine(ENGINE) as e:
        settings(e);neural(e,model)
        for (line,) in db.execute('select payload from samples where split=0 order by id'):
            if time.monotonic()>=deadline:db.close();raise RuntimeError('calibration deadline; model unchanged')
            row=json.loads(line)
            cmd(e,'newgame '+row['game_string']);_,lines=features(e,'alpha-neural');raw=int(lines[2].split()[1])
            target=row['teacher_search_cp']*row['mover']/4
            if not math.isfinite(target):db.close();raise RuntimeError('nonfinite calibration target')
            if abs(target)>=10000:continue
            numerator+=raw*target;denominator+=raw*raw;target_squared+=target*target;count+=1
    db.close()
    if denominator==0 or numerator<=0:raise RuntimeError('no positive finite calibration fit')
    scale=max(.01,min(10.,numerator/denominator))
    rmse=math.sqrt(max(0.,target_squared-2*scale*numerator+scale*scale*denominator)/count)
    manifest.update(score_scale=scale,calibration=dict(positions=count,heldout_excluded=True,cross_split_transpositions_excluded=True,tactical_exclusion_signature=exclusion_signature,corpus_sha256=digest(WORK/args.corpus/'manifest.json')))
    manifest['calibration'].update(rmse_gen1_units=rmse,uncalibrated_rmse_gen1_units=math.sqrt(max(0.,target_squared-2*numerator+denominator)/count),corpus_files={p.name:digest(p) for p in files},engine_sha256=digest(ENGINE),trainer_sha256=digest(REPORT/'trainer-latest-pin.json'))
    atomic(sidecar,manifest);atomic(REPORT/(model.stem+'-calibration.json'),manifest['calibration']|dict(score_scale=scale));print('calibrated',scale,count)
    frozen=WORK/'candidates'/digest(model)/digest(sidecar)
    frozen.mkdir(parents=True,exist_ok=True)
    target=frozen/model.name
    if target.exists() and digest(target)!=digest(model):raise RuntimeError('immutable candidate mismatch')
    if not target.exists():shutil.copyfile(model,target);shutil.copyfile(sidecar,str(target)+'.alpha.json')
    atomic(REPORT/(model.stem+'-candidate.json'),dict(model=str(target.relative_to(ROOT)),sha256=digest(target),sidecar_sha256=digest(str(target)+'.alpha.json'),production_promoted=False))

def arena(args):
    guard();freeze_search();model=Path(args.model or WORK/'nu-baseline.nnue').resolve();opponent=Path(args.opponent or WORK/'gen1.exe').resolve()
    name=args.name;path=REPORT/(name+'.json');deadline=time.monotonic()+args.seconds
    config=dict(candidate_sha256=digest(ENGINE),model_sha256=digest(model),sidecar_sha256=digest(str(model)+'.alpha.json'),opponent_sha256=digest(opponent),games=args.games,threads=args.threads,internal_ms=230,external_ms=250,cap=160,total_budget_mib=32,seed=220700)
    pin=read(REPORT/'nokamute-pin.json')
    if opponent.name=='nokamute.exe' and config['opponent_sha256']!=pin['sha256']:raise RuntimeError('Nokamute pin mismatch')
    if args.games==100:config['seed']=220800
    config['stage']='development';config['opponent_path']=str(opponent);config['opening_manifest']=[dict(seed=config['seed']+i//2,candidate_color=i%2) for i in range(args.games)]
    if args.games==100:
        screens=[read(p) for p in REPORT.glob('*.json')]
        passed=[s for s in screens if s.get('config',{}).get('games')==20 and s['config'].get('candidate_sha256')==config['candidate_sha256'] and s['config'].get('model_sha256')==config['model_sha256'] and s['config'].get('sidecar_sha256')==config['sidecar_sha256'] and s.get('complete') and s.get('valid') and not s.get('resources_uncontrolled') and s.get('points',0)>10]
        gen1=read(REPORT/'gen1.json')['sha256']
        if not any(s['config']['opponent_sha256']==gen1 for s in passed) or not any(s['config']['opponent_sha256']==pin['sha256'] for s in passed):raise RuntimeError('100-game development requires both passing 20-game screens')
    state=read(path) if path.exists() else dict(config=config,games=[],complete=False,valid=True)
    if state['config']!=config:raise RuntimeError('arena resume mismatch')
    if not state['valid']:raise RuntimeError('invalid arena cannot be resumed')
    for index in range(len(state['games']),args.games):
        if time.monotonic()>=deadline:break
        if heavy_conflict():
            state.update(resources_uncontrolled=True,strength_evidence=False,failure='competing heavy job; resumable stop');atomic(path,state)
            raise RuntimeError('competing heavy job; resumable stop')
        for file,key in ((ENGINE,'candidate_sha256'),(model,'model_sha256'),(Path(str(model)+'.alpha.json'),'sidecar_sha256'),(opponent,'opponent_sha256')):
            if digest(file)!=config[key]:raise RuntimeError('arena artifact changed during stage')
        guard();seed=config['seed']+index//2;rng=random.Random(seed);color=index%2;record=dict(index=index,opening_seed=seed,candidate_color=color,moves=[],score=None,termination=None,max_ms=[0.,0.])
        with engine(ENGINE,['--evaluator','neural','--model',model]) as a,engine(opponent) as b:
            players=[a,b] if color==0 else [b,a]
            for e in players:settings(e,args.threads);cmd(e,'newgame Base')
            for ply in range(160):
                if time.monotonic()>=deadline:return
                floors()
                legal=cmd(players[0],'validmoves')[0][0].split(';')
                other=cmd(players[1],'validmoves')[0][0].split(';')
                canonical=lambda moves:{cmd(a,'alpha-moveid '+m)[0][0] for m in moves}
                if canonical(legal)!=canonical(other):record['termination']='rules_divergence';state['valid']=False;break
                side=ply%2
                if ply<4:move=rng.choice(sorted(legal))
                else:
                    requested=time.monotonic()
                    try:lines,t=cmd(players[side],'bestmove seconds 0.230',.250);move=lines[0];record['max_ms'][side]=max(record['max_ms'][side],t*1000)
                    except TimeoutError:record['max_ms'][side]=max(record['max_ms'][side],(time.monotonic()-requested)*1000);record.update(termination='timeout',timeout_side=side,score=float(side!=color));break
                    if cmd(a,'alpha-moveid '+move)[0][0] not in canonical(legal):record.update(termination='illegal',score=float(side!=color));break
                    pv,_=players[side].command('pv')
                    record.setdefault('search',[]).append(dict(ply=ply,move_ms=t*1000,pv=pv[:-1],nodes=None,completed_depth=None,telemetry='pinned UHP exposes PV only'))
                results=[cmd(e,'play '+move)[0][0] for e in players];record['moves'].append(move)
                states=[x.split(';')[1] for x in results]
                if states[0]!=states[1]:record['termination']='rules_divergence';state['valid']=False;break
                if states[0] not in ('InProgress','NotStarted'):
                    record.update(termination='natural',score=.5 if states[0]=='Draw' else float((states[0]=='WhiteWins')==(color==0)));break
            if record['termination'] is None:record.update(termination='ply_cap',score=.5)
        state['games'].append(record);state['complete']=len(state['games'])==args.games;state['points']=sum(g['score'] or 0 for g in state['games']);atomic(path,state)
        print(name,len(state['games']),state['points'],flush=True)
        if not state['valid']:break
    controlled=state['complete'] and state['valid'] and not state.get('resources_uncontrolled')
    state['eligible_for_larger_development']=args.games==20 and controlled and state.get('points',0)>10
    state['gen1_promotion_requirement_met']=args.games==100 and config['opponent_sha256']==read(REPORT/'gen1.json')['sha256'] and controlled and state.get('points',0)>55
    state['promoted']=False;atomic(path,state)

def benchmark(args):
    model=Path(args.model or WORK/'nu-baseline.nnue').resolve();records=[]
    games=['Base']
    for file in sorted((WORK/args.corpus).glob('game-*.jsonl'))[:2]:
        rows=[json.loads(line) for line in file.open()]
        games.extend(row['game_string'] for row in rows if row['ply'] in (12,24,36))
    started=time.monotonic()
    for mode in ('gen1','neural'):
        with engine(ENGINE) as e:
            settings(e,args.threads)
            if mode=='neural':neural(e,model)
            for game in games:
                if time.monotonic()-started>=args.seconds:break
                floors();cmd(e,'newgame '+game)
                legal=cmd(e,'validmoves')[0][0].split(';')
                canonical={cmd(e,'alpha-moveid '+m)[0][0] for m in legal}
                evaluation=[]
                for _ in range(10):evaluation.append(cmd(e,'alpha-eval')[1]*1000)
                diagnostics=features(e,'alpha-neural')[1]+cmd(e,'alpha-neural-bench')[0] if mode=='neural' else []
                search=cmd(e,'alpha-search 3 230')[0]
                try:
                    lines,t=cmd(e,'bestmove time 00:00:00.230',.250)
                    reply=dict(milliseconds=t*1000,legal=cmd(e,'alpha-moveid '+lines[0])[0][0] in canonical,timeout=False)
                except TimeoutError:reply=dict(legal=False,timeout=True)
                records.append(dict(mode=mode,game_sha256=hashlib.sha256(game.encode()).hexdigest(),evaluation_ms=evaluation,diagnostics=diagnostics,search=search,reply=reply))
    result=dict(binary_sha256=digest(ENGINE),model_sha256=digest(model),threads=args.threads,budget_mib=32,cache_reserve_bytes=13*256*1024,records=records,all_legal_and_on_time=all(r['reply']['legal'] and not r['reply']['timeout'] for r in records),loaded_system_guarantee=False)
    atomic(REPORT/(Path(model).stem+'-benchmark.json'),result);print(dict(samples=len(records),all_legal_and_on_time=result['all_legal_and_on_time']))

def costs(args):
    floors();model=Path(args.model or WORK/'nu-baseline.nnue').resolve();rows=[]
    games=['Base']
    for file in sorted((WORK/args.corpus).glob('game-*.jsonl'))[:2]:
        for line in file.open():
            row=json.loads(line)
            if row['ply'] in (12,24,36):games.append(row['game_string'])
    deadline=time.monotonic()+args.seconds
    with engine(ENGINE) as e:
        settings(e);neural(e,model)
        for game in games:
            if time.monotonic()>=deadline:break
            cmd(e,'newgame '+game);cmd(e,'alpha-neural');rows.append(dict(position_sha256=hashlib.sha256(game.encode()).hexdigest(),costs=cmd(e,'alpha-neural-bench')[0]))
    result=dict(binary_sha256=digest(ENGINE),model_sha256=digest(model),samples=rows,stationary_warm_cache=True,quiet_system=False)
    atomic(REPORT/(model.stem+'-costs.json'),result);print(result)

def main():
    global ENGINE
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','parity','schemas','collect','train','calibrate','arena','benchmark','costs']);p.add_argument('--seconds',type=int,default=600);p.add_argument('--games',type=int,default=20);p.add_argument('--threads',type=int,default=1);p.add_argument('--model');p.add_argument('--opponent');p.add_argument('--name',default='nu-vs-gen1');p.add_argument('--stage-id');p.add_argument('--corpus',default='corpus');p.add_argument('--engine')
    p.add_argument('--selection',choices=('regret','mse'),default='regret')
    p.add_argument('--ranking-weight',type=float,default=.25)
    args=p.parse_args()
    if not math.isfinite(args.ranking_weight) or not 0<=args.ranking_weight<=1:p.error('bounded ranking weight required')
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]+',args.name) or not re.fullmatch(r'[A-Za-z0-9_-]+',args.corpus) or args.corpus.lower()=='iota' or (args.stage_id and not re.fullmatch(r'[A-Za-z0-9_-]+',args.stage_id)):p.error('safe report, corpus and stage names required')
    for path in (args.model,args.opponent,args.engine):
        if path and any(part.lower()=='iota' for part in Path(path).resolve().parts):p.error('Iota is excluded')
    if args.engine:ENGINE=Path(args.engine).resolve()
    if not 1<=args.seconds<=7200 or args.games<2 or args.games%2 or not 1<=args.threads<=12:p.error('bounded even games, 1..12 threads, stages <=2 hours required')
    WORK.mkdir(parents=True,exist_ok=True)
    lock=(WORK/'stage.lock').open('a+b');lock.write(b'0');lock.flush();lock.seek(0)
    if os.name=='nt':
        import msvcrt,ctypes
        msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x40)
        if args.mode in ('collect','train','calibrate','arena','benchmark') and heavy_conflict():raise RuntimeError('conflicting heavy campaign')
    try:
        stage=REPORT/'stages'/((args.stage_id or str(time.time_ns()))+'.json')
        identity=dict(mode=args.mode,name=args.name,model=args.model,opponent=args.opponent,games=args.games,threads=args.threads,corpus=args.corpus,binary_sha256=digest(ENGINE))
        if args.mode=='train':identity.update(selection=args.selection,ranking_weight=args.ranking_weight)
        progress,args.seconds=stage_start(stage,identity,args.seconds)
        try:
            {'prepare':lambda _:prepare(),'parity':parity,'schemas':schemas,'collect':collect,'train':train,'calibrate':calibrate,'arena':arena,'benchmark':benchmark,'costs':costs}[args.mode](args)
        except Exception as error:
            progress.update(status='failed',error=repr(error));atomic(stage,progress)
            failure=dict(error=repr(error),time=time.time(),mode=args.mode,name=args.name)
            atomic(REPORT/(args.mode+'-failure.json'),failure)
            atomic(REPORT/(args.mode+'-failure-'+str(time.time_ns())+'.json'),failure)
            if args.mode=='arena':
                path=REPORT/(args.name+'.json')
                if path.exists():
                    state=read(path)
                    recoverable=any(str(error).startswith(prefix) for prefix in ('RAM below','disk reserve','device storage cap','arena resume mismatch','competing heavy job'))
                    state.update(failure=repr(error))
                    if not recoverable:state['valid']=False
                    atomic(path,state)
            raise
        progress.update(status='returned',finished=time.time());atomic(stage,progress)
    finally:lock.close()
if __name__=='__main__':main()
