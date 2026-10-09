"""Publish path-free cache experiment evidence; preserve the full local measurements."""
import argparse
import json
from pathlib import Path

from evidence import atomic_json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError('refusing to overwrite public evidence')
    def read(name):
        return json.loads((args.directory / name).read_text())
    baseline, candidate = read('baseline.json'), read('candidate.json')
    parity, paired = read('parity-retry.json'), read('paired-uhp.json')
    if not parity['equal'] or parity['baseline_sha256'] != baseline['engine_sha256'] or parity['candidate_sha256'] != candidate['engine_sha256']:
        raise RuntimeError('parity evidence does not match benchmark pins')
    result = {'version': 1, 'schema': 7, 'production_default_changed': False,
              'strength_claim': False, 'settings': read('manifest.json'),
              'baseline': baseline, 'candidate': candidate, 'paired_uhp': paired,
              'ordinary_uhp': {'baseline': read('baseline-uhp.json')['summaries'],
                               'candidate': read('candidate-uhp.json')['summaries']},
              'parity': {'equal': True, 'comparisons': len(parity['rows']), 'roots': len(parity['positions']),
                         'schemas': [5, 6, 7], 'scope': 'features-prior-move-score-nodes-pv'},
              'limitations': ['Small development suite; no strength match.',
                              'Ordinary-new allocation requests exclude aligned allocations and are not peak live memory.',
                              'Native search times exclude transport; paired UHP requests include transport.',
                              'Component timing uses 200 iterations per root and is exploratory.',
                              'Schema 7 bypasses the serialized feature cache; no meaningful depth gain established.',
                              'Initial parity harness rejected an early mate completion; harness corrected and failure evidence retained.']}
    serialized = json.dumps(result)
    if ':\\' in serialized or ':/' in serialized or '/Users/' in serialized:
        raise RuntimeError('host path in public evidence')
    atomic_json(args.output, result)


if __name__ == '__main__':
    main()
