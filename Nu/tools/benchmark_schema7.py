"""Consumed native inference and pinned 1/2/4-thread deadline/memory profiles."""
import argparse
import ctypes
import json
from pathlib import Path
import random
import subprocess
import sys
import threading
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from evidence import atomic_json,digest
from train import response,resource_guard
from genseki.uhp import UhpProcess


def memory(pid):
    if sys.platform!='win32':raise RuntimeError('Windows working-set/commit measurement required')
    class Counters(ctypes.Structure):
        _fields_=[('cb',ctypes.c_ulong),('faults',ctypes.c_ulong)]+[(name,ctypes.c_size_t) for name in
            ('peak_working','working','peak_paged','paged','peak_nonpaged','nonpaged','pagefile','peak_pagefile','private')]
    kernel=ctypes.windll.kernel32;kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.OpenProcess.argtypes=[ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
    kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    psapi=ctypes.windll.psapi;psapi.GetProcessMemoryInfo.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong]
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle:raise RuntimeError('cannot measure benchmark process memory')
    try:
        value=Counters();value.cb=ctypes.sizeof(value)
        if not psapi.GetProcessMemoryInfo(handle,ctypes.byref(value),value.cb):raise RuntimeError('memory query failed')
        return dict(working=value.working,peak_working=value.peak_working,commit=value.private,peak_commit=value.peak_pagefile)
    finally:kernel.CloseHandle(handle)


def main():
    p=argparse.ArgumentParser()
    for name in ('engine','referee','cost-engine','models','openings','output'):
        p.add_argument('--'+name,type=Path,nargs='+' if name=='models' else None,required=True)
    p.add_argument('--gen1',type=Path,required=True)
    p.add_argument('--resume',action='store_true')
    args=p.parse_args()
    saved_path=args.output/'benchmark.json'
    saved=json.loads(saved_path.read_text()) if args.resume and saved_path.exists() else None
    if args.output.exists() and saved is None:raise RuntimeError('benchmark evidence is immutable')
    if saved is not None:
        pins=dict(engine_sha256=digest(args.engine),cost_engine_sha256=digest(args.cost_engine),
                  referee_sha256=digest(args.referee),openings_sha256=digest(args.openings),
                  gen1_sha256=digest(args.gen1),models_sha256=[digest(m) for m in args.models])
        if saved.get('version')!=2 or any(saved.get(k)!=v for k,v in pins.items()):
            raise RuntimeError('benchmark resume pin/version mismatch')
    args.output.mkdir(parents=True,exist_ok=True)
    roots=[];referee=UhpProcess([str(args.referee.resolve())])
    try:
        for opening in json.loads(args.openings.read_text())['openings']:
            game=response(referee,'newgame '+opening['game_string'])[0];rng=random.Random(opening['seed']+10000000)
            for ply in range(48):
                if ply in (0,8,20,40):
                    roots.append(dict(game=game,position=response(referee,'genseki-validate-game '+game)[0]))
                moves=response(referee,'validmoves')[0].split(';')
                game=response(referee,'play '+rng.choice(sorted(moves)))[0]
                if game.split(';')[1]!='InProgress':break
    finally:referee.close()
    root_file=args.output/'roots.txt';root_text='\n'.join(r['position'] for r in roots)+'\n'
    if saved is not None:
        if root_file.read_text(encoding='utf8')!=root_text or json.loads((args.output/'roots.json').read_text())!=roots:
            raise RuntimeError('benchmark resume roots mismatch')
    else:
        root_file.write_text(root_text,encoding='utf8');atomic_json(args.output/'roots.json',roots)
    report=dict(version=2,models_sha256=[digest(m) for m in args.models],
                engine_sha256=digest(args.engine),cost_engine_sha256=digest(args.cost_engine),
                referee_sha256=digest(args.referee),openings_sha256=digest(args.openings),
                roots_sha256=digest(root_file),internal_ms=230,external_ms=250,table_mib=16,
                evaluator_plus_table_ceiling=64*1024**2,records=[],gen1_records=[],costs=[],completed=False,
                gen1_sha256=digest(args.gen1))
    if digest(args.gen1)!=json.loads((ROOT/'Alpha/reports/gen2/gen1.json').read_text())['sha256']:
        raise RuntimeError('Gen 1 benchmark pin mismatch')
    if saved is not None:
        keys=('engine_sha256','cost_engine_sha256','referee_sha256','openings_sha256','roots_sha256',
              'gen1_sha256','internal_ms','external_ms','table_mib','evaluator_plus_table_ceiling')
        if any(saved.get(k)!=report[k] for k in keys):raise RuntimeError('benchmark resume pin mismatch')
        report=saved
    atomic_json(args.output/'benchmark.json',report)
    for model in args.models:
        resource_guard()
        if not any(c['model_sha256']==digest(model) for c in report['costs']):
            cost=subprocess.run([str(args.cost_engine.resolve()),str(model.resolve()),str(root_file.resolve())],
                                capture_output=True,text=True,check=True,timeout=120)
            report['costs'].append(dict(json.loads(cost.stdout),model_sha256=digest(model)))
        for threads in (1,2,4):
            for root in roots:
                if any(r['model_sha256']==digest(model) and r['threads']==threads and r['position']==root['position'] for r in report['records']):continue
                resource_guard();peer=UhpProcess([str(args.engine.resolve()),'--model',str(model.resolve())])
                stop=threading.Event();measurements=[];errors=[]
                def sample():
                    while not stop.is_set():
                        try:measurements.append(memory(peer.process.pid))
                        except RuntimeError as error:
                            if peer.process.poll() is None:errors.append(str(error))
                            return
                        stop.wait(.002)
                monitor=threading.Thread(target=sample);monitor.start()
                row=dict(model_sha256=digest(model),threads=threads,position=root['position'],timeout=False)
                try:
                    for option in (f'Threads {threads}','TableMiB 16','BackgroundPondering False','ThreatPlies 0','LateMoveReductions False'):
                        response(peer,'options '+option)
                    response(peer,'newgame '+root['game'])
                    allocations=response(peer,'nu-memory')[0].split()
                    row['allocations']={allocations[i]:int(allocations[i+1]) for i in range(0,len(allocations),2)}
                    started=time.perf_counter()
                    try:lines,elapsed=peer.command('bestmove depthorseconds 64 0.230',.250)
                    except TimeoutError:
                        row.update(timeout=True,latency_ms=(time.perf_counter()-started)*1000)
                    except RuntimeError as error:
                        if str(error)!='UHP engine exited':raise
                        row.update(engine_exit=True,error=str(error),exit_code=peer.process.poll(),
                                   latency_ms=(time.perf_counter()-started)*1000)
                    else:
                        if lines[0].startswith(('err ','invalidmove')):raise RuntimeError(lines)
                        row.update(latency_ms=elapsed*1000,search=response(peer,'nu-searchinfo'))
                        response(peer,'play '+lines[0]);row['legal_reply']=True
                    row['model_file_bytes']=model.stat().st_size
                    row['table_config_bytes']=16*1024**2
                finally:
                    stop.set();monitor.join(1)
                    if monitor.is_alive():raise RuntimeError('memory monitor failed to stop')
                    peer.close()
                if errors or not measurements:raise RuntimeError('missing memory evidence')
                row['memory']={key:max(m[key] for m in measurements) for key in measurements[0]}
                report['records'].append(row);atomic_json(args.output/'benchmark.json',report)
        print('profiled '+model.name,flush=True)
    from gen1_teacher import parse_diagnostics
    with (args.output/'gen1-verbose.log').open('a+',encoding='utf8') as log:
        for root in roots:
            if any(r['position']==root['position'] for r in report['gen1_records']):continue
            resource_guard();peer=UhpProcess([str(args.gen1.resolve())],stderr=log)
            stop=threading.Event();measurements=[]
            def sample_gen1():
                while not stop.is_set():
                    try:measurements.append(memory(peer.process.pid))
                    except RuntimeError:return
                    stop.wait(.002)
            monitor=threading.Thread(target=sample_gen1);monitor.start()
            row=dict(position=root['position'],threads=1,verbose_for_diagnostics=True,timeout=False)
            try:
                for option in ('NumThreads 1','TableSizeMiB 16','BackgroundPondering False','RandomOpening False','Verbose True'):
                    response(peer,'options set '+option)
                response(peer,'newgame '+root['game']);log.seek(0,2);offset=log.tell()
                started=time.perf_counter()
                try:lines,elapsed=peer.command('bestmove depthorseconds 64 0.230',.250)
                except TimeoutError:row.update(timeout=True,latency_ms=(time.perf_counter()-started)*1000)
                else:
                    diagnostic_deadline=time.monotonic()+.1
                    while True:
                        log.seek(offset);diagnostics=log.read()
                        try:parsed=parse_diagnostics(diagnostics);break
                        except RuntimeError as error:
                            if time.monotonic()>=diagnostic_deadline:
                                parsed=dict(completed_depth=None,nodes=None,diagnostic_error=str(error),diagnostics=diagnostics)
                                break
                            time.sleep(.002)
                    row.update(parsed,latency_ms=elapsed*1000,pv=response(peer,'pv'))
                    response(peer,'play '+lines[0]);row['legal_reply']=True
            finally:
                stop.set();monitor.join(1);peer.close()
            if not measurements:raise RuntimeError('missing Gen 1 memory evidence')
            row['memory']={key:max(m[key] for m in measurements) for key in measurements[0]}
            report['gen1_records'].append(row);atomic_json(args.output/'benchmark.json',report)
    report['completed']=True
    report['timeouts']=sum(r['timeout'] for r in report['records'])
    report['gen1_timeouts']=sum(r['timeout'] for r in report['gen1_records'])
    report['engine_exits']=sum(r.get('engine_exit',False) for r in report['records'])
    report['memory_limit_verified']=all(sum(r['allocations'].values())<64*1024**2 and r['memory']['peak_commit']<64*1024**2
                                        for r in report['records'] if r['threads']==1)
    report['memory_limit_verified'] &= all(r['memory']['peak_commit']<64*1024**2 for r in report['gen1_records'])
    atomic_json(args.output/'benchmark.json',report)


if __name__=='__main__':
    from research_job import run
    run(main)
