"""Pinned hybrid ablations and fresh development openings; never promote."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import random
import shutil
import sqlite3
import statistics
import subprocess
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from genseki.uhp import UhpProcess
from evidence import atomic_json,digest
from position_keys import position_key
from train import response,resource_guard
from benchmark_schema7 import memory
from genseki.artifacts import portable_value

TERMS=['neighbors','friendly_surround','queen_control','nearby_beetle','queen_exits','critical_liberties']
CONFIGS=[('plain',None),('full',63)]+[('without_'+name,63^(1<<i)) for i,name in enumerate(TERMS)]


def prepare(directory):
    if directory.exists():raise RuntimeError('study directory is immutable')
    directory.mkdir(parents=True);campaign=ROOT/'Nu/work/schema7-campaign'
    sources={'nu.exe':ROOT/'.tmp/nu-hybrid-study-build/nu.exe',
             'cost.exe':ROOT/'.tmp/nu-hybrid-study-build/nu_campaign_cost.exe',
             'scores.exe':ROOT/'.tmp/nu-hybrid-study-build/nu_hybrid_scores.exe',
             'model.nnue':campaign/'frozen-screen/schema7.nnue',
             'gen1.exe':campaign/'frozen-screen/gen1.exe','rules.exe':campaign/'frozen-screen/rules.exe'}
    pins={}
    for name,source in sources.items():
        shutil.copyfile(source,directory/name);pins[name]=digest(source)
        if digest(directory/name)!=pins[name]:raise RuntimeError('artifact copy mismatch')
    exclusions=json.loads((ROOT/'Nu/reports/schema7/qualification-exclusions.json').read_text())
    forbidden=set(exclusions['positions'])|set(exclusions['opening_families'])
    old=json.loads((campaign/'openings/development-openings.json').read_text())
    forbidden.update(o['key'] for o in old['openings'])
    indexes=[campaign/'corpus/final-index.sqlite',ROOT/'Nu/work/canonical-repair-v3/index.sqlite']
    actual=[]
    for index in indexes:
        if not index.exists():
            if index==indexes[0]:raise RuntimeError('missing authoritative corpus index')
            continue
        with sqlite3.connect(index.resolve().as_uri()+'?mode=ro',uri=True) as db:
            forbidden.update(p for p, in db.execute('select position from exposures'))
            for payload, in db.execute('select payload from samples'):
                row=json.loads(payload)
                if row.get('opening_position'):forbidden.add(position_key(row['opening_position']))
        actual.append(dict(path=str(index.relative_to(ROOT)),sha256=digest(index)))
    fast=ROOT/'Nu/work/fast-schema5-pilot-v2/corpus.jsonl'
    for line in fast.open(encoding='utf8'):
        row=json.loads(line)
        for field in ('position','opening_position','preferred_position','alternative_position'):
            if row.get(field):forbidden.add(position_key(row[field]))
        for child in row.get('alternatives',[])+row.get('observed_children',[]):forbidden.add(position_key(child['position']))
    peer=UhpProcess([str(directory/'rules.exe')]);openings=[]
    try:
        for seed in range(460000,510000):
            resource_guard();rng=random.Random(seed);game=response(peer,'newgame Base')[0];moves=[]
            for _ in range(4):
                legal=sorted(response(peer,'validmoves')[0].split(';'));move=rng.choice(legal)
                moves.append(move);game=response(peer,'play '+move)[0]
            position=response(peer,'genseki-validate-game '+game)[0];key=position_key(position)
            if key in forbidden:continue
            forbidden.add(key);openings.append(dict(seed=seed,moves=moves,game_string=game,position=position,key=key))
            if len(openings)==10:break
        if len(openings)!=10:raise RuntimeError('unable to find disjoint development openings')
        atomic_json(directory/'openings.json',dict(kind='development-fourply',openings=openings))
        roots=[]
        for opening in openings:
            game=response(peer,'newgame '+opening['game_string'])[0];rng=random.Random(opening['seed']+10000000)
            for ply in range(48):
                if ply in (0,8,20,40):roots.append(dict(game=game,position=response(peer,'genseki-validate-game '+game)[0]))
                move=rng.choice(sorted(response(peer,'validmoves')[0].split(';')))
                game=response(peer,'play '+move)[0]
                if game.split(';')[1]!='InProgress':break
        atomic_json(directory/'roots.json',roots)
        (directory/'roots.txt').write_text('\n'.join(r['position'] for r in roots)+'\n',encoding='utf8')
    finally:peer.close()
    for name in ('openings.json','roots.json','roots.txt'):pins[name]=digest(directory/name)
    atomic_json(directory/'manifest.json',dict(version=1,pins=pins,indexes=actual,
        fast_corpus_sha256=digest(fast),exclusions_sha256=digest(ROOT/'Nu/reports/schema7/qualification-exclusions.json'),
        configs=CONFIGS,threads=1,table_mib=16,internal_ms=230,external_ms=250,cap=160,promoted=False))
    print('frozen ten fresh disjoint mirrored openings and '+str(len(roots))+' roots',flush=True)


def checked(directory):
    manifest=json.loads((directory/'manifest.json').read_text())
    for name,sha in manifest['pins'].items():
        if digest(directory/name)!=sha:raise RuntimeError('study pin mismatch: '+name)
    for index in manifest['indexes']:
        if digest(ROOT/index['path'])!=index['sha256']:raise RuntimeError('study corpus pin mismatch')
    if digest(ROOT/'Nu/work/fast-schema5-pilot-v2/corpus.jsonl')!=manifest['fast_corpus_sha256']:
        raise RuntimeError('study baseline corpus pin mismatch')
    if digest(ROOT/'Nu/reports/schema7/qualification-exclusions.json')!=manifest['exclusions_sha256']:
        raise RuntimeError('study exclusions changed')
    return manifest


def benchmark(directory):
    manifest=checked(directory);path=directory/'benchmark.json'
    report=json.loads(path.read_text()) if path.exists() else dict(manifest_sha256=digest(directory/'manifest.json'),costs={},records=[],completed=False)
    if report['manifest_sha256']!=digest(directory/'manifest.json'):raise RuntimeError('benchmark resume mismatch')
    if report['completed']:return
    roots=json.loads((directory/'roots.json').read_text())
    referee=UhpProcess([str(directory/'rules.exe')])
    try:
        for name,mask in CONFIGS:
            if name not in report['costs']:
                resource_guard();command=[str(directory/'cost.exe'),str(directory/'model.nnue'),str(directory/'roots.txt')]
                if mask is not None:command.append(str(mask))
                trials=[json.loads(subprocess.run(command,capture_output=True,text=True,check=True,timeout=120).stdout) for _ in range(3)]
                report['costs'][name]=trials;atomic_json(path,report)
            for index,root in enumerate(roots):
                if any(r['config']==name and r['root']==index for r in report['records']):continue
                resource_guard();peer=UhpProcess([str(directory/'nu.exe'),'--model',str(directory/'model.nnue')])
                stop=threading.Event();measures=[]
                def sample():
                    while not stop.is_set():
                        try:measures.append(memory(peer.process.pid))
                        except RuntimeError:return
                        stop.wait(.003)
                monitor=threading.Thread(target=sample);monitor.start()
                row=dict(config=name,root=index,mask=mask,timeout=False)
                try:
                    for option in ('Threads 1','TableMiB 16','BackgroundPondering False','ThreatPlies 0','LateMoveReductions False'):
                        response(peer,'options '+option)
                    response(peer,'options HybridEvaluation '+('False' if mask is None else 'True'))
                    response(peer,'options HybridWeight 100')
                    response(peer,'options HybridTerms '+str(mask if mask is not None else 63))
                    response(peer,'newgame '+root['game'])
                    allocation=response(peer,'nu-memory')[0].split()
                    row['allocations']={allocation[i]:int(allocation[i+1]) for i in range(0,len(allocation),2)}
                    row['diagnostic']=response(peer,'nu-hybrid-eval')
                    start=time.perf_counter()
                    try:lines,elapsed=peer.command('bestmove depthorseconds 64 0.230',.250)
                    except TimeoutError:row.update(timeout=True,latency_ms=(time.perf_counter()-start)*1000)
                    else:
                        if lines[0].startswith(('err ','invalidmove')):raise RuntimeError(lines)
                        row.update(latency_ms=elapsed*1000,move=lines[0],search=response(peer,'nu-searchinfo'))
                        game=response(peer,'play '+lines[0])[0]
                        reconstructed=response(referee,'genseki-validate-game '+game)[0]
                        if reconstructed!=response(peer,'nu-position')[0]:raise RuntimeError('benchmark board divergence')
                        row['legal']=True
                finally:
                    stop.set();monitor.join(1);peer.close()
                if monitor.is_alive() or not measures:raise RuntimeError('missing bounded memory measurement')
                row['peak_commit_bytes']=max(m['peak_commit'] for m in measures)
                report['records'].append(row);atomic_json(path,report)
            print('profiled '+name,flush=True)
    finally:referee.close()
    report['completed']=True
    report['memory_gate']=all(r['peak_commit_bytes']<64*1024**2 and sum(r['allocations'].values())<64*1024**2 for r in report['records'])
    atomic_json(path,report)


def correlation(a,b):
    if len(a)<2:return None
    am=statistics.mean(a);bm=statistics.mean(b)
    aa=sum((x-am)**2 for x in a);bb=sum((y-bm)**2 for y in b)
    return sum((x-am)*(y-bm) for x,y in zip(a,b))/math.sqrt(aa*bb) if aa and bb else None


def ablate(directory):
    checked(directory);path=directory/'ablation.json'
    if path.exists():raise RuntimeError('ablation evidence is immutable')
    index=ROOT/'Nu/work/schema7-campaign/corpus/final-index.sqlite'
    with sqlite3.connect(index.resolve().as_uri()+'?mode=ro',uri=True) as db:
        rows=[json.loads(p) for p, in db.execute('select payload from samples where split=1')]
    positions=sorted({c['position'] for r in rows for c in r.get('alternatives',[])})
    if not positions:raise RuntimeError('missing held-out decision alternatives')
    score_file=directory/'decision-positions.txt';score_file.write_text('\n'.join(positions)+'\n',encoding='utf8')
    process=subprocess.run([str(directory/'scores.exe'),str(directory/'model.nnue'),str(score_file)],capture_output=True,text=True,check=True,timeout=120)
    values=[list(map(int,line.split())) for line in process.stdout.splitlines()]
    if len(values)!=len(positions) or any(len(v)!=8 for v in values):raise RuntimeError('invalid independent score output')
    scores=dict(zip(positions,values));metrics={}
    for name,mask in CONFIGS:
        regrets=[];agreements=0
        for row in rows:
            children=row.get('alternatives',[])
            if len(children)<2:continue
            targets=[c['cp']*row['mover'] for c in children];predictions=[]
            for child in children:
                data=scores[child['position']];bonus=sum(data[2+i] for i in range(6) if mask is not None and mask&(1<<i))
                predictions.append(max(-8000,min(8000,data[0]+bonus))*row['mover'])
            chosen=max(range(len(children)),key=lambda i:predictions[i]);regret=max(targets)-targets[chosen]
            regrets.append(regret);agreements+=regret==0
        metrics[name]=dict(decisions=len(regrets),regret_cp=statistics.mean(regrets),top_choice_agreement=agreements/len(regrets))
    priors=[v[1] for v in values];terms={name:dict(prior_correlation=correlation([v[2+i] for v in values],priors),
        mean_abs_cp=statistics.mean(abs(v[2+i]) for v in values)) for i,name in enumerate(TERMS)}
    atomic_json(path,dict(index_sha256=digest(index),model_sha256=digest(directory/'model.nnue'),
        decision_positions=len(positions),position_file_sha256=digest(score_file),metrics=metrics,terms=terms,
        limitations=['Offline move regret and correlation are diagnostics, not match strength.',
                    'These held-out decisions are now development-exposed.',
                    'Prior correlation does not establish harmful double-counting.']))
    print(json.dumps(metrics),flush=True)


def balanced_cost(directory):
    checked(directory);path=directory/'balanced-cost.json'
    if path.exists():raise RuntimeError('balanced cost evidence is immutable')
    report=dict(order=[],trials={name:[] for name,_ in CONFIGS},completed=False)
    for trial in range(5):
        order=list(CONFIGS)
        random.Random(1701+trial).shuffle(order)
        report['order'].append([name for name,_ in order])
        for name,mask in order:
            resource_guard();command=[str(directory/'cost.exe'),str(directory/'model.nnue'),str(directory/'roots.txt')]
            if mask is not None:command.append(str(mask))
            result=json.loads(subprocess.run(command,capture_output=True,text=True,check=True,timeout=120).stdout)
            report['trials'][name].append(result);atomic_json(path,report)
    report['completed']=True;atomic_json(path,report)


def report(directory):
    manifest=checked(directory)
    benchmark=json.loads((directory/'benchmark.json').read_text())
    balanced=json.loads((directory/'balanced-cost.json').read_text())
    ablation=json.loads((directory/'ablation.json').read_text())
    if not benchmark['completed'] or not benchmark['memory_gate'] or not balanced['completed']:
        raise RuntimeError('incomplete benchmark/cost gate')
    profiles={}
    for name,mask in CONFIGS:
        rows=[r for r in benchmark['records'] if r['config']==name];trials=balanced['trials'][name]
        if not rows or len(trials)!=5:raise RuntimeError('missing ablation evidence')
        valid=[r for r in rows if r.get('legal')]
        profiles[name]=dict(roots=len(rows),legal_replies=len(valid),timeouts=sum(r['timeout'] for r in rows),
            completed_depth_sum=sum(int(r['search'][0].split()[1]) for r in valid),
            nodes_sum=sum(int(r['search'][0].split()[3]) for r in valid),
            maximum_latency_ms=max(r['latency_ms'] for r in rows),
            maximum_peak_commit_bytes=max(r['peak_commit_bytes'] for r in rows),
            evaluator_plus_table_bytes=max(sum(r['allocations'].values()) for r in rows),
            cost_median_ns={key:statistics.median(t[key] for t in trials) for key in
                ('evaluation_ns','make_evaluate_unmake_ns','reconstruction_ns')},
            cost_range_ns={key:[min(t[key] for t in trials),max(t[key] for t in trials)] for key in
                ('evaluation_ns','make_evaluate_unmake_ns')})
    screens={}
    for name in ('plain','gen1'):
        path=directory/('screen-'+name+'.json');match=json.loads(path.read_text());games=match['games']
        if not match['completed'] or match['rejected'] or len(games)!=20:raise RuntimeError('incomplete/rejected screen')
        for field,value in dict(hybrid=True,hybrid_weight=100,hybrid_terms=63,threads=1,table_mib=16,
                                internal_ms=230,milliseconds=250,cap=160,depth_limit=64).items():
            if match.get(field)!=value:raise RuntimeError('match setting mismatch '+field)
        for field,file in dict(engine_sha256='nu.exe',model_sha256='model.nnue',referee_sha256='rules.exe',
                               opponent_sha256='nu.exe' if name=='plain' else 'gen1.exe',openings_sha256='openings.json').items():
            if match[field]!=manifest['pins'][file]:raise RuntimeError('match pin mismatch')
        if name=='plain' and match['opponent_model_sha256']!=manifest['pins']['model.nnue']:
            raise RuntimeError('plain opponent model mismatch')
        scores=Counter(g['score'] for g in games)
        screens[name]=dict(points=match['points'],wins=scores[1],draws=scores[.5],losses=scores[0],
            natural_wins=sum(g['termination']=='natural' and g['score']==1 for g in games),
            terminations=dict(Counter(g['termination'] for g in games)),
            candidate_timeouts=sum(g['termination']=='timeout' and g['timeout_side']=='Nu' for g in games),
            opponent_timeouts=sum(g['termination']=='timeout' and g['timeout_side']=='Opponent' for g in games),
            maximum_move_ms=max(g['max_move_ms'] for g in games),sha256=digest(path),
            games=[{k:g[k] for k in ('pair','opening_seed','nu_color','score','result','termination','max_move_ms','timeout_side')} for g in games])
    output=ROOT/'Nu/reports/hybrid-v1/results.json'
    if output.exists():raise RuntimeError('public evidence is immutable')
    evidence=dict(version=1,manifest=manifest,profiles=profiles,ablation=ablation,screens=screens,
        default_enabled=False,promoted=False,qualification_run=False,
        input_hashes={name:digest(directory/name) for name in
            ('manifest.json','benchmark.json','balanced-cost.json','ablation.json')},
        limitations=['Small development screens do not establish production qualification.',
                    'Every timeout counts as a loss, including opponent forfeits.',
                    'No natural win against Alpha Gen 1 occurred.',
                    'Ablations use existing held-out Gen 1-labeled corpus decisions, now development-exposed.',
                    'Offline regret/correlation do not establish ablated match strength.',
                    'Search profiles were sequential; balanced cost trials used five shuffled rounds.',
                    'Do not compare this Gen 1 score causally with earlier screens on different openings.'])
    atomic_json(output,portable_value(ROOT,evidence));print(json.dumps(screens),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--phase',choices=('prepare','benchmark','ablate','balanced_cost','report'),required=True);args=p.parse_args()
    globals()[args.phase](args.directory.resolve())


if __name__=='__main__':
    from research_job import run
    run(main)
