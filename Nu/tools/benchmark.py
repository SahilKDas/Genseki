"""Repeated latency/depth/thread/profile measurements on fixed development positions."""
import argparse
import json
from pathlib import Path
import random
import subprocess
import sys
import time
from evidence import atomic_json,digest
from train import response,resource_guard
from genseki.uhp import UhpProcess

def working_set(pid):
    import os
    if os.name!='nt':return None
    import ctypes
    class Counters(ctypes.Structure):
        _fields_=[('size',ctypes.c_uint32),('faults',ctypes.c_uint32)]+[(name,ctypes.c_size_t) for name in
                  ('peak','working','peak_pool','pool','peak_nonpaged','nonpaged','pagefile','peak_pagefile')]
    kernel=ctypes.WinDLL('kernel32');kernel.OpenProcess.restype=ctypes.c_void_p
    kernel.OpenProcess.argtypes=[ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32];kernel.CloseHandle.argtypes=[ctypes.c_void_p]
    handle=kernel.OpenProcess(0x410,False,pid)
    if not handle:return None
    try:
        memory=Counters();memory.size=ctypes.sizeof(memory)
        api=ctypes.WinDLL('psapi').GetProcessMemoryInfo
        api.argtypes=[ctypes.c_void_p,ctypes.POINTER(Counters),ctypes.c_uint32]
        if not api(handle,ctypes.byref(memory),memory.size):return None
        return dict(working_set_bytes=memory.working,peak_working_set_bytes=memory.peak,peak_committed_bytes=memory.peak_pagefile)
    finally:kernel.CloseHandle(handle)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--engine',type=Path,required=True);p.add_argument('--model',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--threads',type=int,nargs='+',default=[1,2,4,8,12]);p.add_argument('--load-workers',type=int,default=0)
    p.add_argument('--suite',type=Path);p.add_argument('--threat-plies',type=int,default=0);p.add_argument('--lmr',action='store_true')
    args=p.parse_args()
    if not 0<=args.load_workers<=2 or not 1<=args.repeats<=30 or not all(1<=n<=12 for n in args.threads):p.error('invalid bounded benchmark settings')
    if args.output.exists():raise RuntimeError('refusing to overwrite benchmark evidence')
    resource_guard();rng=random.Random(823);positions=[]
    engine=UhpProcess([str(args.engine),'--model',str(args.model)])
    try:
        if args.suite:positions=json.loads(args.suite.read_text())['positions']
        else:
            game='Base';response(engine,'newgame Base')
            for ply in range(21):
                if ply in (0,4,8,12,16,20):positions.append(game)
                moves=response(engine,'validmoves')[0].split(';')
                game=response(engine,'play '+rng.choice(moves))[0]
                if game.split(';')[1]!='InProgress':break
    finally:engine.close()
    # Explicit bounded load mode is part of this one benchmark job, not another campaign.
    loaders=[];rows=[]
    try:
        for _ in range(args.load_workers):
            loaders.append(subprocess.Popen([sys.executable,'-c','import time\nend=time.monotonic()+180\nx=1\nwhile time.monotonic()<end:x=(x*1664525+1013904223)&0xffffffff']))
        for threads in args.threads:
            for repeat in range(args.repeats):
                for index,game in enumerate(positions):
                    resource_guard();engine=UhpProcess([str(args.engine),'--model',str(args.model)])
                    try:
                        effective=response(engine,f'options Threads {threads}')
                        if not effective or effective[0].split(';')[2]!=str(threads):raise RuntimeError('thread setting readback mismatch')
                        response(engine,'options Profile True')
                        response(engine,f'options ThreatPlies {args.threat_plies}')
                        response(engine,f'options LateMoveReductions {"True" if args.lmr else "False"}')
                        table=response(engine,'options TableMiB 16')
                        if not table or table[0].split(';')[2]!='16':raise RuntimeError('table setting readback mismatch')
                        response(engine,'newgame '+game)
                        legal=set(response(engine,'validmoves')[0].split(';'))
                        started=time.perf_counter()
                        try:
                            lines,elapsed=engine.command('bestmove depthorseconds 64 .23',.25)
                            move=lines[0]
                            if move not in legal:raise RuntimeError('illegal benchmark reply')
                        except TimeoutError:
                            rows.append(dict(threads=threads,repeat=repeat,position=index,timeout=True,
                                milliseconds=(time.perf_counter()-started)*1000,depth=None,nodes=None,score=None,
                                legal_reply=None,profile={},failure='external-deadline'))
                            continue
                        fields=response(engine,'nu-searchinfo')[0].split();profile=response(engine,'nu-profile')[0].split()
                        memory=working_set(engine.process.pid)
                        if memory and max(memory['peak_working_set_bytes'],memory['peak_committed_bytes'])>64*1024**2:raise RuntimeError('common 64 MiB process memory ceiling exceeded')
                        rows.append(dict(threads=threads,repeat=repeat,position=index,move=move,milliseconds=elapsed*1000,
                                         timeout=elapsed*1000>250,depth=int(fields[1]),nodes=int(fields[3]),score=int(fields[5]),
                                         legal_reply=True,verified_threads=threads,table_request_mib=16,
                                         memory=memory,
                                         profile={profile[i]:int(profile[i+1]) for i in range(0,len(profile),2)}))
                    finally:engine.close()
    except BaseException as error:
        atomic_json(args.output,dict(completed=False,error=repr(error),measurements=rows,
                    engine_sha256=digest(args.engine),model_sha256=digest(args.model)))
        raise
    finally:
        for loader in loaders:
            if loader.poll() is None:loader.terminate()
            loader.wait()
    summaries=[]
    for threads in args.threads:
        measurements=[r for r in rows if r['threads']==threads]
        summaries.append(dict(threads=threads,timeouts=sum(r['timeout'] for r in measurements),
                             total_depth=sum(r['depth'] or 0 for r in measurements),max_ms=max(r['milliseconds'] for r in measurements)))
    eligible=[s for s in summaries if not s['timeouts']]
    selected=max(eligible,key=lambda s:(s['total_depth'],-s['max_ms']))['threads'] if eligible else None
    report=dict(engine_sha256=digest(args.engine),model_sha256=digest(args.model),positions=positions,measurements=rows,
                summaries=summaries,selected_threads=selected,load_workers=args.load_workers,
                threat_plies=args.threat_plies,lmr=args.lmr,selection_is_performance_only=True,completed=True,common_memory_ceiling_bytes=64*1024**2)
    atomic_json(args.output,report);print(json.dumps(summaries))

if __name__=='__main__':
    from research_job import run
    run(main)
