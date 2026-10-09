"""Compare frozen pre/post cache-isolation features and single-thread searches."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import random

from evidence import atomic_json, digest
from research_job import run
from train import resource_guard, response
from genseki.uhp import UhpProcess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--models', type=Path, nargs='+', required=True)
    parser.add_argument('--roots', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError('refusing to overwrite parity evidence')
    roots = [row['position'] for row in json.loads(args.roots.read_text())['results']['components']]
    rng = random.Random(1701)
    with closing(UhpProcess([str(args.baseline.resolve()), '--model', str(args.models[0].resolve())])) as engine:
        response(engine, 'newgame Base')
        for ply in range(16):
            if ply % 2 == 0:
                roots.append(response(engine, 'nu-position')[0])
            moves = response(engine, 'validmoves')[0].split(';')
            game = response(engine, 'play ' + rng.choice(moves))[0]
            if game.split(';')[1] != 'InProgress':
                break
    rows = []
    try:
        for model in args.models:
            for index, root in enumerate(roots):
                resource_guard()
                lanes = []
                for binary in [args.baseline, args.candidate]:
                    with closing(UhpProcess([str(binary.resolve()), '--model', str(model.resolve())])) as engine:
                        response(engine, 'options Threads 1')
                        response(engine, 'options TableMiB 16')
                        response(engine, 'nu-loadposition ' + root)
                        features = response(engine, 'nu-features')
                        prior = response(engine, 'nu-prior')
                        move = response(engine, 'bestmove depthorseconds 2 5')
                        search = response(engine, 'nu-searchinfo')
                        fields = search[0].split()
                        if int(fields[1]) != 2 and not (int(fields[1]) > 0 and abs(int(fields[5])) > 90000):
                            raise RuntimeError('incomplete fixed-depth parity search')
                        lanes.append({'features': features, 'prior': prior, 'move': move, 'search': search})
                if lanes[0] != lanes[1]:
                    raise RuntimeError('fixed-depth or evaluation parity failure')
                rows.append({'model_sha256': digest(model), 'root': index, 'equal': True,
                             'search': lanes[0]['search']})
    except BaseException:
        atomic_json(args.output.with_suffix('.failure.json'), {'completed_rows': rows})
        raise
    atomic_json(args.output, {'version': 1, 'baseline_sha256': digest(args.baseline),
                             'candidate_sha256': digest(args.candidate), 'positions': roots,
                             'rows': rows, 'equal': True})
    print(json.dumps({'equal': True, 'comparisons': len(rows), 'roots': len(roots)}))


if __name__ == '__main__':
    run(main)
