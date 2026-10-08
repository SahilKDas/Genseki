"""Frozen Gen 1/neural diagnostics through one identical Alpha search executable."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from genseki.resources import job_lock,team_job_path,heavy_job_path,available_ram
from genseki.artifacts import sha256_file
from genseki.uhp import UhpProcess


def telemetry(lines,elapsed):
    head=next((re.fullmatch(r'score (-?\d+) static (-?\d+) move (.+)',line) for line in lines if line.startswith('score ')),None)
    stats=next((re.search(r'Explored (\d+) nodes to depth (\d+)',line) for line in lines if 'Explored ' in line),None)
    if not head or not stats:raise ValueError('missing completed-depth telemetry')
    return dict(score=int(head[1]),static=int(head[2]),move=head[3],nodes=int(stats[1]),completed_depth=int(stats[2]),elapsed_ms=elapsed*1000)


def checked(engine,text,timeout=5):
    lines,elapsed=engine.command(text,timeout)
    if any(line.startswith(('err ','invalidmove')) for line in lines):raise ValueError('engine rejected diagnostic configuration or replay')
    return [line for line in lines if line!='ok'],elapsed


def configure(engine,mode,model):
    offered={line.split(';')[0] for line in checked(engine,'options')[0]}
    verified={}
    options={'NumThreads':'1','BackgroundPondering':'False','RandomOpening':'False','TableSizeMiB':'32'}
    for flag in ('TacticalOrdering','ForcedDefenseExtensions'):
        if flag in offered:options[flag]='False'
    for name,value in options.items():
        checked(engine,f'options set {name} {value}')
        lines,_=checked(engine,'options get '+name)
        fields=next((line.split(';') for line in lines if line.startswith(name+';')),[])
        if len(fields)<3 or fields[2]!=value:raise ValueError('effective settings mismatch')
        verified[name]=value
    if mode=='neural':
        checked(engine,'options set ModelPath '+str(model.resolve()))
        checked(engine,'options set Evaluator neural')
    else:checked(engine,'options set Evaluator gen1')
    evaluator=checked(engine,'options get Evaluator')[0]
    if not any(line.split(';')[2]==mode for line in evaluator if line.startswith('Evaluator;')):
        raise ValueError('effective evaluator mismatch')
    return verified


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for option in ('binary','model','fixtures','output'):p.add_argument('--'+option,type=Path,required=True)
    p.add_argument('--seconds',type=int,default=120);p.add_argument('--positions',type=int,default=6)
    p.add_argument('--depth',type=int,default=3)
    args=p.parse_args()
    if not 1<=args.seconds<=7200 or not 1<=args.positions<=100 or not 1<=args.depth<=8:p.error('bounded diagnostic stage required')
    if args.output.exists():p.error('immutable diagnostic output already exists')
    for path in (args.binary,args.model,args.fixtures,args.output):
        if not path.resolve().is_relative_to(ROOT) or 'iota' in [part.lower() for part in path.parts]:p.error('repository artifacts outside Iota required')
    identities={key:sha256_file(path) for key,path in (('binary',args.binary),('model',args.model),('calibration',Path(str(args.model)+'.alpha.json')),('fixtures',args.fixtures))}
    fixtures=json.loads(args.fixtures.read_text())
    records=[r for r in fixtures['records'] if r['split']=='development' and r['proof']['status']=='complete' and r['proof']['kind'] in ('immediate_win','mandatory_defense')]
    if not records:p.error('no complete development tactics; no decision claim permitted')
    report=dict(schema_version=1,kind='development-diagnostics',identities=identities,records=[],completed=False,
                equal_search_binary=True,total_memory_budget_mib=32,actual_allocations_verified=False,
                limitations=['Diagnostic TT request bytes are recorded; allocator/worker/cache allocations require independent measurement before strength matches.'],training_launched=False)
    deadline=time.monotonic()+args.seconds
    with job_lock(team_job_path(ROOT)),job_lock(heavy_job_path(ROOT)):
        if os.name=='nt':
            k=ctypes.windll.kernel32;k.GetCurrentProcess.restype=ctypes.c_void_p;k.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_ulong];k.SetPriorityClass(k.GetCurrentProcess(),0x40)
        for record in records[:args.positions]:
            for kind,depth,internal,external in (('fixed_depth',args.depth,1500,1800),('fixed_time',8,230,250)):
                searches={}
                for mode in ('gen1','neural'):
                    if available_ram()<512*1024**2 or time.monotonic()+external/1000+1>=deadline:
                        raise RuntimeError('diagnostic resource or stage limit')
                    if any(sha256_file(path)!=identities[key] for key,path in (('binary',args.binary),('model',args.model),('calibration',Path(str(args.model)+'.alpha.json')),('fixtures',args.fixtures))):raise ValueError('immutable diagnostic artifact changed')
                    engine=UhpProcess([str(args.binary.resolve())])
                    try:
                        settings=configure(engine,mode,args.model)
                        checked(engine,'newgame '+record['game_string'])
                        diagnostics=checked(engine,'alpha-neural')[0] if mode=='neural' else []
                        try:
                            lines,elapsed=checked(engine,f'alpha-search {depth} {internal}',external/1000)
                            result=telemetry(lines,elapsed)
                            expected=record['proof']['winning_moves'] if record['proof']['kind']=='immediate_win' else record['proof']['safe_moves']
                            expected_ids={checked(engine,'alpha-moveid '+move)[0][0] for move in expected}
                            chosen=checked(engine,'alpha-moveid '+result['move'])[0][0]
                            result.update(solved=chosen in expected_ids,completed_requested_depth=result['completed_depth']>=depth,
                                          within_deadline=result['elapsed_ms']<=external)
                        except TimeoutError:
                            result=dict(timeout=True,solved=None,completed_depth=None,within_deadline=False)
                        result.update(effective_settings=settings,diagnostics=diagnostics)
                        searches[mode]=result
                    finally:engine.close()
                report['records'].append(dict(id=record['id'],kind=kind,tactic=record['proof']['kind'],searches=searches,
                    equal_completed_depth=(len({s.get('completed_depth') for s in searches.values()})==1 and all(s.get('completed_depth') is not None for s in searches.values())) if kind=='fixed_depth' else None))
                args.output.parent.mkdir(parents=True,exist_ok=True)
                pending=args.output.with_suffix('.pending');pending.write_text(json.dumps(report,indent=2));pending.replace(args.output)
        report['completed']=True
        args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(records=len(report['records']),completed=True,strength_claim=False)))


if __name__=='__main__':main()
