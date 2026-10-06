"""One-shot qualification. Development must clear the gate before final seeds exist."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from evidence import atomic_json, REPETITION_POLICY, NOKAMUTE_REVISION, NOKAMUTE_SHA256

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--opponent', type=Path, required=True)
    parser.add_argument('--development', type=Path, required=True)
    parser.add_argument('--incumbent-match', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    report = json.loads(args.development.read_text())
    if digest(args.opponent)!=NOKAMUTE_SHA256 or report.get('opponent_revision')!=NOKAMUTE_REVISION:
        raise RuntimeError('qualification requires the pinned Nokamute reference artifact')
    if not report.get('completed') or len(report['games'])!=report.get('expected_games'):
        raise RuntimeError('development run is incomplete or lacks completion evidence')
    if report.get('rejected') or len(report['games']) < 100 or report['points'] / len(report['games']) <= .55:
        raise RuntimeError('development result does not project above 55%; final qualification remains sealed')
    frozen = dict(engine_sha256=digest(args.engine), model_sha256=digest(args.model),
                  opponent_sha256=digest(args.opponent), milliseconds=250, threads=report['threads'], cap=160,
                  repetition_policy=REPETITION_POLICY,threat_plies=report.get('threat_plies',0),lmr=report.get('lmr',False))
    incumbent=json.loads(args.incumbent_match.read_text())
    if not incumbent.get('completed') or incumbent.get('rejected') or len(incumbent['games'])<20 or incumbent['points']/len(incumbent['games'])<.5:
        raise RuntimeError('incumbent confirmation gate failed')
    if incumbent['model_sha256']!=frozen['model_sha256'] or incumbent['engine_sha256']!=frozen['engine_sha256'] or not incumbent.get('opponent_model_sha256'):
        raise RuntimeError('incumbent match artifact mismatch')
    for key in ('engine_sha256', 'model_sha256', 'opponent_sha256'):
        if frozen[key] != report[key]: raise RuntimeError('development artifact mismatch')
    if report['milliseconds'] != 250 or not 1<=report['threads']<=12 or report['cap'] != 160 or report.get('repetition_policy')!=REPETITION_POLICY:
        raise RuntimeError('development configuration mismatch')
    args.directory.mkdir(parents=True, exist_ok=True)
    # Exclusive creation consumes this candidate's single attempt before seeds are revealed.
    registry = Path(__file__).resolve().parents[1] / 'work' / 'qualification-attempts'
    registry.mkdir(parents=True, exist_ok=True)
    attempt = registry / (frozen['model_sha256'] + '.attempt.json')
    with attempt.open('x') as handle: json.dump(frozen, handle, indent=2)
    seed_base = secrets.randbelow(1 << 30) + 1000000
    with (args.directory / 'seeds.json').open('x') as handle:
        json.dump(dict(base=seed_base, count=50), handle)
    output = args.directory / 'qualification.json'
    subprocess.run([sys.executable, str(Path(__file__).with_name('arena.py')),
                    '--engine', str(args.engine), '--model', str(args.model),
                    '--opponent', str(args.opponent), '--games', '100', '--seed-base', str(seed_base),
                    '--threads',str(frozen['threads']),'--threat-plies',str(frozen['threat_plies']),
                    *(['--lmr'] if frozen['lmr'] else []),'--output', str(output)], check=True)
    for key, path in [('engine_sha256', args.engine), ('model_sha256', args.model), ('opponent_sha256', args.opponent)]:
        if digest(path) != frozen[key]:raise RuntimeError('artifact changed during qualification')
    final = json.loads(output.read_text())
    final.update(kind='qualification', passed=final.get('completed',False) and not final.get('rejected') and len(final['games'])==100 and final['points'] > 55, frozen=frozen)
    atomic_json(output,final)
    if final['passed']:
        temporary = args.directory / 'champion.pending'
        temporary.write_text(json.dumps(frozen, indent=2))
        os.replace(temporary, args.directory / 'champion.json')
    print(f"{final['points']}/100; passed={final['passed']}")

if __name__ == '__main__': main()
