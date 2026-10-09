"""Alternating before/after UHP measurements on the frozen categorized roots."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import time

from benchmark import working_set
from evidence import atomic_json, digest
from research_job import run
from train import resource_guard, response
from genseki.uhp import UhpProcess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--threads', type=int, nargs='+', default=[1, 2, 4])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if len(set(args.threads)) != len(args.threads) or not all(1 <= value <= 12 for value in args.threads):
        parser.error('threads must be distinct values between 1 and 12')
    directory = args.directory
    output = args.output or directory / 'paired-uhp.json'
    if output.exists():
        raise RuntimeError('refusing to overwrite paired measurements')
    manifest = json.loads((directory / 'manifest.json').read_text())
    for name, checksum in manifest['artifacts'].items():
        if digest(directory / name) != checksum:
            raise RuntimeError('frozen baseline changed')
    candidate = json.loads((directory / 'candidate.json').read_text())
    if digest(directory / 'candidate-engine.exe') != candidate['engine_sha256']:
        raise RuntimeError('frozen candidate changed')
    pins = {name: digest(directory / name) for name in ['baseline-engine.exe', 'candidate-engine.exe', 'model.nnue']}
    roots = json.loads((directory / 'baseline.json').read_text())['results']['components']
    rows = []
    root_identity = [{'category': r['category'], 'position': r['position']} for r in roots]
    identity = {'pins': pins, 'threads': args.threads, 'repeats': 3, 'roots': root_identity,
                'internal_ms': 230, 'external_ms': 250, 'table_mib': 16}
    if args.resume:
        saved = json.loads(output.with_suffix('.failure.json').read_text())
        if any(saved.get(key) != value for key, value in identity.items()):
            raise RuntimeError('resume identity differs')
        rows = saved['measurements']
        expected = [(lane, repeat, threads, root['category']) for repeat in range(3)
                    for threads in args.threads for root in roots
                    for lane in (['baseline', 'candidate'] if repeat % 2 == 0 else ['candidate', 'baseline'])]
        actual = [(r['lane'], r['repeat'], r['threads'], r['category']) for r in rows]
        if actual != expected[:len(actual)]:
            raise RuntimeError('resume measurements are not a completed prefix')
    retained = len(rows)
    request_index = 0
    try:
        for repeat in range(3):
            for threads in args.threads:
                for root in roots:
                    lanes = ['baseline', 'candidate'] if repeat % 2 == 0 else ['candidate', 'baseline']
                    for lane in lanes:
                        request_index += 1
                        if request_index <= retained:
                            continue
                        resource_guard()
                        with closing(UhpProcess([str((directory / (lane + '-engine.exe')).resolve()),
                                                 '--model', str((directory / 'model.nnue').resolve())])) as engine:
                            response(engine, f'options Threads {threads}')
                            response(engine, 'options TableMiB 16')
                            response(engine, 'options Profile True')
                            response(engine, 'nu-loadposition ' + root['position'])
                            legal = response(engine, 'validmoves')[0].split(';')
                            row = {'lane': lane, 'repeat': repeat, 'threads': threads, 'category': root['category']}
                            start = time.perf_counter()
                            try:
                                lines, elapsed = engine.command('bestmove depthorseconds 64 .23', .25)
                            except TimeoutError:
                                row.update(timeout=True, milliseconds=(time.perf_counter()-start)*1000,
                                           depth=0, nodes=0, legal=False)
                                rows.append(row)
                                continue
                            if lines[0] not in legal:
                                raise RuntimeError('illegal measured reply')
                            info = response(engine, 'nu-searchinfo')[0].split()
                            profile = response(engine, 'nu-profile')[0].split()
                            row.update(timeout=elapsed > .25, milliseconds=elapsed*1000,
                                       depth=int(info[1]), nodes=int(info[3]), score=int(info[5]), legal=True,
                                       profile=dict(zip(profile[::2], map(int, profile[1::2]))),
                                       memory=working_set(engine.process.pid))
                            rows.append(row)
    except BaseException:
        atomic_json(output.with_suffix('.failure.json'), {**identity, 'measurements': rows})
        raise
    if any(digest(directory / name) != checksum for name, checksum in pins.items()):
        raise RuntimeError('artifact changed during measurements')
    summaries = []
    for lane in ['baseline', 'candidate']:
        for threads in args.threads:
            subset = [row for row in rows if row['lane'] == lane and row['threads'] == threads]
            summaries.append({'lane': lane, 'threads': threads, 'depth_total': sum(row['depth'] for row in subset),
                              'nodes_total': sum(row['nodes'] for row in subset),
                              'timeouts': sum(row['timeout'] for row in subset),
                              'max_ms': max(row['milliseconds'] for row in subset)})
    atomic_json(output, {'version': 1, 'pins': pins, 'table_mib': 16, 'internal_ms': 230,
                        'external_ms': 250, 'threads': args.threads, 'repeats': 3,
                        'roots': [{'category': r['category'], 'position': r['position']} for r in roots],
                        'measurements': rows, 'summaries': summaries})
    print(json.dumps(summaries))


if __name__ == '__main__':
    run(main)
