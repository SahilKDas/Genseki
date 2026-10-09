"""Register a search generation only from its immutable complete point gate."""
import argparse
import json
from pathlib import Path
import struct

from arena import VALIDATION_POLICY, MEMORY_POLICY
from evidence import atomic_json,digest
from incumbent import checked_pair,verified_settings

ROOT=Path(__file__).resolve().parents[2]


def scored(row):
    reason=row['termination']
    if reason=='timeout':
        if row['timeout_side'] not in ('Nu','Opponent'):raise RuntimeError('invalid timeout side')
        return float(row['timeout_side']=='Opponent')
    if reason in ('ply_cap','repetition'):
        if row['result']!='Draw':raise RuntimeError('invalid adjudicated result')
        return .5
    if reason!='natural':raise RuntimeError('unsupported result')
    if row['result']=='Draw':return .5
    if row['result'] not in ('WhiteWins','BlackWins'):raise RuntimeError('invalid natural result')
    return float((row['result']=='WhiteWins')==(row['nu_color']=='white'))


def complete(report):
    if not report.get('completed') or report.get('rejected') or report.get('expected_games')!=20 or len(report['games'])!=20:
        raise RuntimeError('incomplete or rejected gate')
    settings=dict(milliseconds=250,internal_ms=230,threads=8,cap=160,depth_limit=64,table_mib=16,
                  background_pondering=False,validation_policy=VALIDATION_POLICY,memory_policy=MEMORY_POLICY)
    if any(report.get(key)!=value for key,value in settings.items()):raise RuntimeError('gate configuration mismatch')
    for i,row in enumerate(report['games']):
        if row['pair']!=i//2 or row['nu_color']!=('white' if i%2==0 else 'black') or row['score']!=scored(row):
            raise RuntimeError('score or mirrored sequence mismatch')
    if report['points']!=sum(scored(row) for row in report['games']):raise RuntimeError('point total mismatch')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--directory',type=Path,required=True);p.add_argument('--public-evidence',type=Path,required=True)
    p.add_argument('--generation',type=int,choices=[9,10],required=True)
    args=p.parse_args();d=args.directory.resolve();public=args.public_evidence.resolve()
    output=ROOT/'Nu/incumbents'/f'schema{args.generation}.json'
    if output.exists():raise RuntimeError('incumbent registration is immutable')
    if not d.is_relative_to(ROOT) or not public.is_relative_to(ROOT):raise RuntimeError('evidence escapes workspace')
    choice=json.loads((d/'selected.json').read_text());gate=json.loads((d/'gate.json').read_text())
    alpha=json.loads((d/'alpha.json').read_text());decision=json.loads((d/'gate-decision.json').read_text())
    complete(gate);complete(alpha)
    if gate['points']<13 or not decision['passed'] or decision['report_sha256']!=digest(d/'gate.json') or decision['selection_sha256']!=digest(d/'selected.json'):
        raise RuntimeError('point gate failed or changed')
    for name,sha in choice['pins'].items():
        if digest(d/(name+('.nnue' if name=='model' else '.exe')))!=sha:raise RuntimeError('frozen artifact changed')
    for report in (gate,alpha):
        if report['engine_sha256']!=choice['pins']['candidate'] or report['model_sha256']!=choice['pins']['model']:
            raise RuntimeError('candidate identity mismatch')
    if gate['opponent_sha256']!=choice['pins']['baseline'] or alpha['opponent_sha256']!=choice['pins']['alpha']:
        raise RuntimeError('opponent identity mismatch')
    if gate['openings_sha256']!=choice['gate_openings_sha256'] or alpha['openings_sha256']!=gate['openings_sha256']:
        raise RuntimeError('opening identity mismatch')
    options=choice['settings'];names={'ThreatPlies':'threat_plies','LateMoveReductions':'lmr','CooperativeOrdering':'cooperative_ordering','RootPVS':'root_pvs','RootPVFirst':'root_pv_first'}
    for report in (gate,alpha):
        if not report.get('deadline_guard') or any(report.get(field,False)!=options.get(name,False) for name,field in names.items()):
            raise RuntimeError('selected policy mismatch')
    exported=json.loads((public/'export.json').read_text())
    for name in ('gate.json','alpha.json','selected.json'):
        row=next(item for item in exported['files'] if item['file']==name)
        if row['private_original_sha256']!=digest(d/name) or row['public_sha256']!=digest(public/name):
            raise RuntimeError('public evidence does not match private source')
    if args.generation==9:
        predecessor=dict(generation=8,engine_sha256=gate['opponent_sha256'],model_sha256=gate['opponent_model_sha256'])
        frozen=ROOT/'Nu/work/schema8-v1/benchmark-checked'
        if predecessor['engine_sha256']!=digest(frozen/'engine.exe') or predecessor['model_sha256']!=digest(frozen/'schema8.nnue'):
            raise RuntimeError('not the frozen schema-8 predecessor')
    else:
        prior=json.loads((ROOT/'Nu/incumbents/schema9.json').read_text());checked_pair(ROOT,prior)
        predecessor=dict(generation=9,engine_sha256=prior['required_pair']['engine_sha256'],model_sha256=prior['required_pair']['model_sha256'])
        if gate['opponent_sha256']!=predecessor['engine_sha256'] or gate['opponent_model_sha256']!=predecessor['model_sha256']:
            raise RuntimeError('not the promoted schema-9 predecessor')
        if gate.get('opponent_config')!=prior['uhp_settings']:raise RuntimeError('predecessor policy mismatch')
    pair=dict(engine=(d/'candidate.exe').relative_to(ROOT).as_posix(),model=(d/'model.nnue').relative_to(ROOT).as_posix(),
              engine_sha256=choice['pins']['candidate'],model_sha256=choice['pins']['model'])
    schema=struct.unpack_from('<I',(d/'model.nnue').read_bytes(),8)[0]
    settings=dict(Threads=8,TableMiB=16,BackgroundPondering=False,DeadlineGuard=True,**options)
    record=dict(role='qualified-research-generation',research_generation=args.generation,status='user-gate-promoted',
                feature_schema=schema,feature_contract='unchanged-schema8-weights',new_weights=False,
                required_pair=pair,uhp_settings=settings,predecessor=predecessor,production_default_changed=False,
                sealed_qualification=False,promotion_authority='explicit user: at least 13/20 mirrored 250ms versus predecessor',
                gate=dict(points=gate['points'],games=20,minimum_points=13),alpha_screen=dict(points=alpha['points'],games=20),
                evidence={name:dict(path=(public/name).relative_to(ROOT).as_posix(),sha256=digest(public/name)) for name in ('gate.json','alpha.json','selected.json')})
    verified_settings(record);checked_pair(ROOT,record);atomic_json(output,record)
    print(f"Research generation {args.generation} promoted: {gate['points']}/20; Alpha {alpha['points']}/20")


if __name__=='__main__':main()
