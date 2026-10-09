"""Development selection followed by a single disjoint twenty-game challenger gate."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

from evidence import atomic_json,digest
from search_probe import POLICIES


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--mode',choices=['ablations','gate','alpha','confirm'],required=True)
    args=p.parse_args();d=args.directory.resolve()
    if args.mode=='confirm':
        for mode in ('gate','alpha'):
            subprocess.run([sys.executable,str(Path(__file__).resolve()),'--directory',str(d),'--mode',mode],check=True,timeout=7250)
        return
    pins=json.loads((d/'pins.json').read_text())
    for name,value in pins.items():
        if digest(d/(name+('.nnue' if name=='model' else '.exe')))!=value:raise RuntimeError('artifact mismatch')
    def match(name,settings,games,openings,alpha=False):
        output=d/(name+'.json')
        command=[sys.executable,str(Path(__file__).with_name('arena.py')),
            '--engine',str(d/'candidate.exe'),'--model',str(d/'model.nnue'),
            '--opponent',str(d/('alpha.exe' if alpha else 'baseline.exe')),
            '--referee',str(d/'referee.exe'),'--games',str(games),'--threads','8',
            '--openings',str(d/openings),'--deadline-guard','--candidate-only-selectivity','--output',str(output)]
        if not alpha:command+=['--opponent-model',str(d/'model.nnue')]
        command+=['--threat-plies',str(settings['ThreatPlies'])]
        if settings['LateMoveReductions']:command+=['--lmr']
        if settings['CooperativeOrdering']:command+=['--cooperative-ordering']
        if settings.get('RootPVS',False):command+=['--root-pvs']
        if output.exists():command+=['--resume']
        print('Running '+name,flush=True)
        subprocess.run(command,check=True,timeout=7250)
        report=json.loads(output.read_text())
        if not report.get('completed') or report.get('rejected') or len(report['games'])!=games:
            raise RuntimeError('invalid development result')
        return report
    selected=d/'selected.json'
    if args.mode=='ablations':
        if selected.exists():raise RuntimeError('selection is already frozen')
        probe=json.loads((d/'probe.json').read_text())
        if not probe['completed']:raise RuntimeError('unfinished timing probe')
        summaries=[]
        policies=probe['policies']
        for policy in policies:
            report=match('ablation-'+policy,policies[policy],6,'ablation-openings.json')
            natural=sum(g['score'] for g in report['games'] if g['termination']=='natural')
            forfeits=sum(g['termination']=='timeout' and g['timeout_side']=='Nu' for g in report['games'])
            depth=next(s['depths'] for s in probe['summaries'] if s['policy']==policy)
            summaries.append(dict(policy=policy,points=report['points'],natural_points=natural,own_timeouts=forfeits,probe_depths=depth,
                                  report_sha256=digest(d/('ablation-'+policy+'.json'))))
        # Fixed tie-breaks: points, natural points, fewer own forfeits, then probe depth.
        best=max(summaries,key=lambda s:(s['points'],s['natural_points'],-s['own_timeouts'],s['probe_depths']))
        atomic_json(selected,dict(version=1,policy=best['policy'],pins=pins,settings=policies[best['policy']],
                    deadline_guard=True,summaries=summaries,gate_openings_sha256=digest(d/'gate-openings.json'),
                    selection_rule='points-natural-fewer-timeouts-depth-v1',promoted=False))
        print('Frozen policy '+best['policy'],flush=True)
    else:
        choice=json.loads(selected.read_text())
        if choice['pins']!=pins or digest(d/'gate-openings.json')!=choice['gate_openings_sha256']:
            raise RuntimeError('selection identity changed')
        alpha=args.mode=='alpha'
        report=match('alpha' if alpha else 'gate',choice['settings'],20,'alpha-openings.json' if alpha else 'gate-openings.json',alpha)
        if not alpha:
            atomic_json(d/'gate-decision.json',dict(version=1,passed=report['points']>=13,points=report['points'],games=20,
                        report_sha256=digest(d/'gate.json'),selection_sha256=digest(selected),promoted=False))
        print(str(report['points'])+'/20',flush=True)


if __name__=='__main__':main()
