"""One-shot qualification. Development must clear the gate before final seeds exist."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import struct
import subprocess
import sys
from evidence import atomic_json, REPETITION_POLICY, NOKAMUTE_REVISION, NOKAMUTE_SHA256

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--opponent', type=Path, required=True)
    parser.add_argument('--referee', type=Path, required=True)
    parser.add_argument('--openings',type=Path)
    parser.add_argument('--development', type=Path, required=True)
    parser.add_argument('--incumbent-match', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    with args.model.open('rb') as model:
        header=model.read(12)
    if len(header)<12:raise RuntimeError('invalid qualification model')
    if struct.unpack_from('<I',header,8)[0] in (7,8) and not args.openings:
        raise RuntimeError('canonical fast schemas require their frozen qualification opening reservation')
    if args.openings:
        sealed=json.loads(args.openings.read_text())
        if sealed.get('kind')!='reserved-qualification' or len(sealed.get('openings',[]))!=50 or sealed.get('referee_sha256')!=digest(args.referee):
            raise RuntimeError('need the matching frozen fifty-opening qualification reservation')
    report = json.loads(args.development.read_text())
    if digest(args.opponent)!=NOKAMUTE_SHA256 or report.get('opponent_revision')!=NOKAMUTE_REVISION:
        raise RuntimeError('qualification requires the pinned Nokamute reference artifact')
    if not report.get('completed') or len(report['games'])!=report.get('expected_games'):
        raise RuntimeError('development run is incomplete or lacks completion evidence')
    if report.get('rejected') or len(report['games']) < 100 or report['points'] / len(report['games']) <= .55:
        raise RuntimeError('development result does not project above 55%; final qualification remains sealed')
    frozen = dict(engine_sha256=digest(args.engine), model_sha256=digest(args.model),
                  openings_sha256=digest(args.openings) if args.openings else None,
                  referee_sha256=digest(args.referee),validation_policy=__import__('arena').VALIDATION_POLICY,depth_limit=64,
                  opponent_sha256=digest(args.opponent), milliseconds=250, threads=report['threads'], cap=160,
                  repetition_policy=REPETITION_POLICY,threat_plies=report.get('threat_plies',0),lmr=report.get('lmr',False))
    incumbent=json.loads(args.incumbent_match.read_text())
    if not incumbent.get('completed') or incumbent.get('rejected') or len(incumbent['games'])!=incumbent.get('expected_games') or len(incumbent['games'])<20 or incumbent['points']/len(incumbent['games'])<.5:
        raise RuntimeError('incumbent confirmation gate failed')
    if incumbent['model_sha256']!=frozen['model_sha256'] or incumbent['engine_sha256']!=frozen['engine_sha256'] or not incumbent.get('opponent_model_sha256'):
        raise RuntimeError('incumbent match artifact mismatch')
    for key in ('engine_sha256', 'model_sha256', 'opponent_sha256'):
        if frozen[key] != report[key]: raise RuntimeError('development artifact mismatch')
    if report['milliseconds'] != 250 or not 1<=report['threads']<=12 or report['cap'] != 160 or report.get('repetition_policy')!=REPETITION_POLICY:
        raise RuntimeError('development configuration mismatch')
    for evidence in (report, incumbent):
        expected=dict(milliseconds=250,internal_ms=230,threads=frozen['threads'],cap=160,
                      memory_policy=__import__('arena').MEMORY_POLICY,
                      referee_sha256=frozen['referee_sha256'],validation_policy=frozen['validation_policy'],depth_limit=64,
                      repetition_policy=REPETITION_POLICY,threat_plies=frozen['threat_plies'],
                      lmr=frozen['lmr'],table_mib=16,background_pondering=False,random_opening=False)
        if any(evidence.get(key)!=value for key,value in expected.items()):
            raise RuntimeError('confirmation search configuration mismatch')
    args.directory.mkdir(parents=True, exist_ok=True)
    # Exclusive creation consumes this candidate's single attempt before seeds are revealed.
    registry = Path(__file__).resolve().parents[1] / 'work' / 'qualification-attempts'
    registry.mkdir(parents=True, exist_ok=True)
    attempt = registry / (frozen['model_sha256'] + '.attempt.json')
    with attempt.open('x') as handle: json.dump(frozen, handle, indent=2)
    if args.openings:
        seed_base=1000000
    else:
        seed_base = secrets.randbelow(1 << 30) + 1000000
        with (args.directory / 'seeds.json').open('x') as handle:
            json.dump(dict(base=seed_base, count=50), handle)
    output = args.directory / 'qualification.json'
    subprocess.run([sys.executable, str(Path(__file__).with_name('arena.py')),
                    '--engine', str(args.engine), '--model', str(args.model),
                    '--opponent', str(args.opponent), '--games', '100', '--seed-base', str(seed_base),
                    '--referee',str(args.referee),
                    *(['--openings',str(args.openings)] if args.openings else []),
                    '--threads',str(frozen['threads']),'--threat-plies',str(frozen['threat_plies']),
                    *(['--lmr'] if frozen['lmr'] else []),'--output', str(output)], check=True)
    for key, path in [('engine_sha256', args.engine), ('model_sha256', args.model), ('opponent_sha256', args.opponent),('referee_sha256',args.referee)]:
        if digest(path) != frozen[key]:raise RuntimeError('artifact changed during qualification')
    if args.openings and digest(args.openings)!=frozen['openings_sha256']:
        raise RuntimeError('qualification opening reservation changed')
    final = json.loads(output.read_text())
    final.update(kind='qualification', passed=final.get('completed',False) and not final.get('rejected') and len(final['games'])==100 and final['points'] > 55, frozen=frozen)
    atomic_json(output,final)
    if final['passed']:
        temporary = args.directory / 'champion.pending'
        temporary.write_text(json.dumps(frozen, indent=2))
        os.replace(temporary, args.directory / 'champion.json')
    print(f"{final['points']}/100; passed={final['passed']}")

if __name__ == '__main__': main()
