"""Compare a combined engine against a frozen evaluator/search contract."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'Nu/tools'))
sys.path.insert(0, str(ROOT))
from evidence import atomic_json, digest
from genseki.uhp import UhpProcess
from train import response, resource_guard


def main():
    parser = argparse.ArgumentParser()
    for name in ('engine', 'reference', 'positions', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--model', type=Path)
    parser.add_argument('--schema', type=int, choices=range(1, 7), required=True)
    parser.add_argument('--searches', type=int, default=12)
    parser.add_argument('--expected-reference-sha256', required=True)
    parser.add_argument('--expected-model-sha256')
    args = parser.parse_args()
    if not 0 <= args.searches <= 24:
        parser.error('search parity is bounded to 24 roots')
    if digest(args.reference) != args.expected_reference_sha256:
        raise RuntimeError('frozen reference hash mismatch')
    if args.model and digest(args.model) != args.expected_model_sha256:
        raise RuntimeError('trained model hash mismatch')
    if args.output.exists():
        raise RuntimeError('refusing to overwrite parity evidence')
    if args.positions.suffix == '.sqlite':
        with sqlite3.connect(args.positions.resolve().as_uri() + '?mode=ro', uri=True) as db:
            rows = [json.loads(payload) for (payload,) in db.execute('select payload from samples order by id limit 1001')]
    else:
        rows = []
        with args.positions.open() as source:
            for line in source:
                rows.append(json.loads(line))
                if len(rows) > 1000:
                    raise RuntimeError('position check exceeds 1000-row bound')
    if not rows or len(rows) > 1000:
        raise RuntimeError('need 1..1000 fixed development positions')
    identity = dict(engine_sha256=digest(args.engine), reference_sha256=digest(args.reference),
                    model_sha256=digest(args.model) if args.model else None,
                    positions_sha256=digest(args.positions), schema=args.schema)
    engines = []
    try:
        for path in (args.engine, args.reference):
            invocation = [str(path)] + (['--model', str(args.model)] if args.model else
                                       ['--feature-schema', str(args.schema)])
            peer = UhpProcess(invocation)
            engines.append(peer)
            if response(peer, 'nu-feature-schema') != [str(args.schema)]:
                raise RuntimeError('unexpected evaluator schema')
            for option in ('Threads 1', 'TableMiB 16', 'BackgroundPondering False',
                           'ThreatPlies 0', 'LateMoveReductions False'):
                response(peer, 'options ' + option)
        for row in rows:
            resource_guard()
            for peer in engines:
                response(peer, 'nu-loadposition ' + row['position'])
            if response(engines[0], 'nu-features') != response(engines[1], 'nu-features'):
                raise RuntimeError('feature/inference mismatch at ' + row['position'])
        searched = 0
        for index in range(min(args.searches, len(rows))):
            row = rows[index * len(rows) // min(args.searches, len(rows))]
            resource_guard()
            for peer in engines:
                response(peer, 'nu-loadposition ' + row['position'])
            moves = [response(peer, 'bestmove depth 1') for peer in engines]
            infos = [response(peer, 'nu-searchinfo') for peer in engines]
            if moves[0] != moves[1] or infos[0] != infos[1]:
                raise RuntimeError('fixed-depth move/score/node/PV mismatch at ' + row['position'])
            searched += 1
        for path, key in ((args.engine, 'engine_sha256'), (args.reference, 'reference_sha256'),
                          (args.positions, 'positions_sha256')):
            if digest(path) != identity[key]:
                raise RuntimeError('immutable input changed during parity check')
        if args.model and digest(args.model) != identity['model_sha256']:
            raise RuntimeError('model changed during parity check')
        report = dict(identity, passed=True, feature_score_positions=len(rows),
                      fixed_depth_searches=searched)
        atomic_json(args.output, report)
        print(json.dumps(report), flush=True)
    finally:
        for peer in engines:
            peer.close()


if __name__ == '__main__':
    from research_job import run
    run(main)
