"""Immutable search ablations and replay-derived deadline regression roots."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import shutil

from benchmark import working_set
from evidence import atomic_json, digest
from freeze_openings import opening
from research_job import check_deadline, run
from train import resource_guard, response
from genseki.uhp import UhpProcess


POLICIES = {
    'guard': dict(ThreatPlies=0, LateMoveReductions=False, CooperativeOrdering=False),
    'threat': dict(ThreatPlies=1, LateMoveReductions=False, CooperativeOrdering=False),
    'lmr': dict(ThreatPlies=0, LateMoveReductions=True, CooperativeOrdering=False),
    'both': dict(ThreatPlies=1, LateMoveReductions=True, CooperativeOrdering=False),
    'coordination': dict(ThreatPlies=1, LateMoveReductions=True, CooperativeOrdering=True),
}


def main():
    p=argparse.ArgumentParser()
    for name in ('engine','baseline','model','referee','alpha','directory'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--repeats',type=int,default=3)
    p.add_argument('--root-pvs',action='store_true')
    p.add_argument('--deep-threat',action='store_true')
    p.add_argument('--scheduler-ablation',action='store_true')
    p.add_argument('--record-isa',action='store_true')
    p.add_argument('--seed-base',type=int,default=190100)
    p.add_argument('--predecessor-record',type=Path)
    args=p.parse_args()
    if args.directory.exists():raise RuntimeError('immutable experiment already exists')
    if not 1<=args.repeats<=10:raise RuntimeError('invalid repeat count')
    resource_guard();args.directory.mkdir(parents=True)
    sources=dict(candidate=args.engine,baseline=args.baseline,model=args.model,referee=args.referee,alpha=args.alpha)
    pins={}
    for name,source in sources.items():
        target=args.directory/(name+('.nnue' if name=='model' else '.exe'))
        shutil.copy2(source,target);pins[name]=digest(target)
    atomic_json(args.directory/'pins.json',pins)
    if args.predecessor_record:
        from incumbent import checked_pair,verified_settings
        record=json.loads(args.predecessor_record.read_text());checked_pair(Path(__file__).resolve().parents[2],record)
        if record['required_pair']['engine_sha256']!=pins['baseline'] or record['required_pair']['model_sha256']!=pins['model']:
            raise RuntimeError('predecessor pair mismatch')
        settings=verified_settings(record)
        if not settings:raise RuntimeError('missing predecessor configuration')
        atomic_json(args.directory/'predecessor-config.json',settings)
    root=Path(__file__).resolve().parents[1]
    benchmark=json.loads((root/'reports/schema8-v1/benchmark-checked.json').read_text())
    roots=[dict(category=r['category'],position=r['position']) for r in benchmark['native']['8']['components']]
    with closing(UhpProcess([str((args.directory/'referee.exe').resolve())])) as referee:
        for name in ('strength-schema7','strength-alpha-g1'):
            report=json.loads((root/'reports/schema8-v1'/f'{name}.json').read_text())
            for game in report['games']:
                if game['timeout_side']!='Nu':continue
                response(referee,'newgame Base')
                for move in game['moves']:game_string=response(referee,'play '+move)[0]
                position=response(referee,'genseki-validate-game '+game_string)[0]
                roots.append(dict(category='timeout-'+name+'-'+str(game['pair']),position=position))
        used=set(json.loads((root/'work/schema7-campaign/openings/exclusions.json').read_text())['opening_families'])
        for prior in (root/'work').glob('search9-*/gate-openings.json'):
            used.update(row['key'] for row in json.loads(prior.read_text())['openings'])
        for prior in (root/'work').glob('search10-*/gate-openings.json'):
            used.update(row['key'] for row in json.loads(prior.read_text())['openings'])
        for name,count,seed in [('ablation-openings',3,args.seed_base),('gate-openings',10,args.seed_base+800),('alpha-openings',10,args.seed_base+800)]:
            if name=='alpha-openings':
                shutil.copy2(args.directory/'gate-openings.json',args.directory/'alpha-openings.json');continue
            rows=[]
            while len(rows)<count:
                check_deadline();row=opening(referee,seed);seed+=1
                if row['key'] in used:continue
                rows.append(row);used.add(row['key'])
            atomic_json(args.directory/(name+'.json'),dict(version=1,kind='development',openings=rows))
    atomic_json(args.directory/'roots.json',roots)
    rows=[]
    policies={name:{**settings,**({'RootPVS':True} if args.root_pvs else {})} for name,settings in POLICIES.items()}
    if args.deep_threat:
        policies['deep-threat']=dict(ThreatPlies=2,LateMoveReductions=False,CooperativeOrdering=False,RootPVS=args.root_pvs)
    if args.scheduler_ablation:
        if not args.root_pvs:raise RuntimeError('scheduler ablation requires root PVS')
        policies={name:{**policies[base], 'RootPVFirst':first} for name,base,first in
                  [('parallel','guard',False),('parallel-lmr','lmr',False),('pv-first','guard',True),('pv-first-lmr','lmr',True)]}
    try:
        for repeat in range(args.repeats):
            for policy in policies:
                for item in roots:
                    check_deadline();resource_guard()
                    with closing(UhpProcess([str((args.directory/'candidate.exe').resolve()),'--model',str((args.directory/'model.nnue').resolve())])) as peer:
                        response(peer,'options Threads 8');response(peer,'options TableMiB 16')
                        response(peer,'options Profile True');response(peer,'options DeadlineGuard True')
                        for option,value in policies[policy].items():
                            response(peer,'options '+option+' '+(str(value) if not isinstance(value,bool) else str(value)))
                        response(peer,'nu-loadposition '+item['position'])
                        legal=response(peer,'validmoves')[0].split(';')
                        row=dict(policy=policy,repeat=repeat,category=item['category'])
                        if args.record_isa:row['accumulator_isa']=response(peer,'nu-accumulator-isa')[0]
                        try:lines,elapsed=peer.command('bestmove depthorseconds 64 .23',.25)
                        except TimeoutError:
                            rows.append(dict(**row,timeout=True));continue
                        if not lines or lines[0] not in legal:raise RuntimeError('illegal probe reply')
                        info=response(peer,'nu-searchinfo')[0].split()
                        timing=response(peer,'nu-timing')[0].split()
                        profile=response(peer,'nu-profile')[0].split()
                        memory=working_set(peer.process.pid)
                        if memory and max(memory['peak_working_set_bytes'],memory['peak_committed_bytes'])>64*1024**2:
                            raise RuntimeError('allocation ceiling exceeded')
                        rows.append(dict(**row,timeout=elapsed>.25,ms=elapsed*1000,depth=int(info[1]),nodes=int(info[3]),
                                         timing=dict(zip(timing[::2],map(int,timing[1::2]))),profile=dict(zip(profile[::2],map(int,profile[1::2]))),memory=memory))
        if any(digest(args.directory/(name+('.nnue' if name=='model' else '.exe')))!=value for name,value in pins.items()):
            raise RuntimeError('frozen artifact changed')
    finally:
        atomic_json(args.directory/'probe.json',dict(pins=pins,measurements=rows,completed=len(rows)==args.repeats*len(policies)*len(roots),
                    policies=policies,summaries=[dict(policy=name,timeouts=sum(r['timeout'] for r in rows if r['policy']==name),
                    depths=sum(r.get('depth',0) for r in rows if r['policy']==name),nodes=sum(r.get('nodes',0) for r in rows if r['policy']==name)) for name in policies]))


if __name__=='__main__':run(main)
