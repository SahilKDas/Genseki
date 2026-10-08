"""Bounded, pinned coordination screen; no promotion or sealed openings."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
import subprocess
from contextlib import closing
from research_job import run, check_deadline
from evidence import atomic_json
from arena import main as arena_main, command
from genseki.uhp import UhpProcess
from train import resource_guard

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'Nu/work/coordination-v1'
SOURCE=ROOT/'Nu/work/hybrid-study-v1'

def publish():
    manifest=json.loads((OUT/'manifest.json').read_text())
    for name,sha in manifest['pins'].items():
        if hashlib.sha256((OUT/name).read_bytes()).hexdigest()!=sha:
            raise RuntimeError('frozen artifact changed')
    screen=json.loads((OUT/'screen.json').read_text())
    if not screen['completed'] or screen['rejected'] or len(screen['games'])!=20:
        raise RuntimeError('screen incomplete or invalid')
    benchmark=json.loads((OUT/'benchmark.json').read_text())
    summary=dict(version=1,manifest=manifest,
                 benchmark=benchmark,points=screen['points'],expected_games=20,
                 games=[{k:v for k,v in game.items() if k not in ('moves','searches')} for game in screen['games']],
                 limitations=['Previously exposed development openings',
                              'Current legal coverage is not a forced multi-move surround',
                              'Native cost measurement is one sequential trial',
                              'Both sides use ThreatPlies 2; not the zero-threat production configuration'],
                 promoted=False)
    output=ROOT/'Nu/reports/coordination-v1/results.json'
    if output.exists() and json.loads(output.read_text())!=summary:raise RuntimeError('refusing to overwrite evidence')
    atomic_json(output,summary)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    files={'nu.exe':ROOT/'.tmp/nu-hybrid-study-build/nu.exe',
           'cost.exe':ROOT/'.tmp/nu-hybrid-study-build/nu_campaign_cost.exe',
           'model.nnue':SOURCE/'model.nnue','rules.exe':SOURCE/'rules.exe',
           'openings.json':SOURCE/'openings.json','roots.json':SOURCE/'roots.json'}
    pins={}
    for name,source in files.items():
        target=OUT/name
        if not target.exists():shutil.copy2(source,target)
        pins[name]=hashlib.sha256(target.read_bytes()).hexdigest()
    manifest=dict(version=1,pins=pins,terms=64,weight=100,threat_plies=2,threads=1,
                  table_mib=16,internal_ms=230,external_ms=250,cap=160,
                  openings_note='Previously exposed development openings; not confirmation or qualification.')
    path=OUT/'manifest.json'
    if path.exists() and json.loads(path.read_text())!=manifest:raise RuntimeError('manifest changed')
    atomic_json(path,manifest)
    benchmark_path=OUT/'benchmark.json'
    if not benchmark_path.exists():
        roots=json.loads((OUT/'roots.json').read_text())
        rows=[]
        for enabled in (False,True):
            with closing(UhpProcess([str(OUT/'nu.exe'),'--model',str(OUT/'model.nnue')])) as peer:
                for option in ('Threads 1','TableMiB 16','BackgroundPondering False','ThreatPlies 2','HybridTerms 64'):
                    command(peer,'options '+option)
                command(peer,'options HybridEvaluation '+str(enabled))
                for root in roots[:12]:
                    check_deadline()
                    resource_guard()
                    command(peer,'newgame '+root['game'])
                    start=time.perf_counter()
                    for _ in range(20):command(peer,'nu-hybrid-eval')
                    cost=(time.perf_counter()-start)*1000/20
                    try:
                        reply,elapsed=command(peer,'bestmove depthorseconds 64 0.230',.250)
                        info=command(peer,'nu-searchinfo')[0]
                        command(peer,'play '+reply[0])
                        memory=command(peer,'nu-memory')[0]
                        rows.append(dict(enabled=enabled,eval_protocol_ms=cost,move_ms=elapsed*1000,info=info,memory=memory,timeout=False))
                    except TimeoutError:
                        rows.append(dict(enabled=enabled,timeout=True));break
        positions=OUT/'positions.txt'
        positions.write_text('\n'.join(root['position'] for root in roots)+'\n')
        native_cost={}
        for mode,mask in [('plain',None),('coordination','64')]:
            args=[str(OUT/'cost.exe'),str(OUT/'model.nnue'),str(positions)]
            if mask:args.append(mask)
            native_cost[mode]=json.loads(subprocess.check_output(args,text=True,timeout=120))
        atomic_json(benchmark_path,dict(manifest=manifest,rows=rows,native_cost=native_cost))
    sys.argv=['arena','--engine',str(OUT/'nu.exe'),'--model',str(OUT/'model.nnue'),
              '--opponent',str(OUT/'nu.exe'),'--opponent-model',str(OUT/'model.nnue'),
              '--referee',str(OUT/'rules.exe'),'--openings',str(OUT/'openings.json'),
              '--games','20','--milliseconds','250','--threat-plies','2',
              '--hybrid','--hybrid-terms','64','--output',str(OUT/'screen.json'),'--resume']
    arena_main()
    publish()

if __name__=='__main__':run(main)
