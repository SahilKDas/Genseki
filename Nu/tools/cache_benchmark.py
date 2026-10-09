"""Freeze and profile the schema-7 cache-isolation experiment without changing defaults."""
import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess

from evidence import atomic_json, digest
from research_job import check_deadline, run
from train import resource_guard


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--benchmark', type=Path, required=True)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--lane', choices=['baseline', 'candidate'], required=True)
    args = parser.parse_args()
    resource_guard()
    args.output.mkdir(parents=True, exist_ok=True)
    manifest_path = args.output / 'manifest.json'
    report_path = args.output / (args.lane + '.json')
    if report_path.exists():
        raise RuntimeError('refusing to overwrite completed evidence')
    if struct.unpack_from('<I', args.model.read_bytes(), 8)[0] != 7:
        raise RuntimeError('cache experiment requires an actual schema-7 model')
    if args.lane == 'baseline':
        if manifest_path.exists():
            raise RuntimeError('baseline already frozen')
        manifest = {'version': 1, 'schema': 7, 'table_mib': 16, 'internal_ms': 230,
                    'external_ms': 250, 'threads': [1, 2, 4], 'repeats': 3,
                    'allocation_scope': 'ordinary-new-requests-not-peak-memory', 'artifacts': {}}
        for name, source in [('baseline-engine.exe', args.engine),
                             ('baseline-benchmark.exe', args.benchmark), ('model.nnue', args.model)]:
            destination = args.output / name
            if destination.exists():
                raise RuntimeError('partial freeze exists; preserve and use a new output directory')
            shutil.copy2(source, destination)
            manifest['artifacts'][name] = digest(destination)
        atomic_json(manifest_path, manifest)
    else:
        manifest = json.loads(manifest_path.read_text())
        if digest(args.model) != manifest['artifacts']['model.nnue']:
            raise RuntimeError('candidate model differs from frozen baseline')
        for name, source in [('candidate-engine.exe', args.engine), ('candidate-benchmark.exe', args.benchmark)]:
            destination = args.output / name
            if destination.exists():
                raise RuntimeError('candidate artifact already exists')
            shutil.copy2(source, destination)
    for name, checksum in manifest['artifacts'].items():
        if digest(args.output / name) != checksum:
            raise RuntimeError('frozen artifact changed')
    check_deadline()
    binary = args.output / (args.lane + '-benchmark.exe')
    completed = subprocess.run([str(binary.resolve()), str((args.output / 'model.nnue').resolve())],
                               capture_output=True, text=True, timeout=180)
    if completed.returncode:
        atomic_json(args.output / (args.lane + '-failure.json'),
                    {'returncode': completed.returncode, 'stderr': completed.stderr})
        raise RuntimeError('benchmark failed; retained diagnostic evidence')
    result = json.loads(completed.stdout)
    if args.lane == 'candidate':
        previous = json.loads((args.output / 'baseline.json').read_text())['results']
        if [row['position'] for row in previous['components']] != [row['position'] for row in result['components']]:
            raise RuntimeError('benchmark roots differ')
    atomic_json(report_path, {'version': 1, 'lane': args.lane,
                            'engine_sha256': digest(args.output / (args.lane + '-engine.exe')),
                            'benchmark_sha256': digest(binary),
                            'model_sha256': manifest['artifacts']['model.nnue'], 'results': result})
    print(json.dumps({'lane': args.lane, 'searches': len(result['search']),
                      'deadline_failures': sum(row['deadline_failure'] for row in result['search']),
                      'depth_total': sum(row['depth'] for row in result['search'])}))


if __name__ == '__main__':
    run(main)
