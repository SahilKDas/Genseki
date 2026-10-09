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
    args = parser.parse_args()
    directory = args.directory
    output = directory / 'paired-uhp.json'
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
    try:
        for repeat in range(3):
            for threads in [1, 2, 4]:
                for root in roots:
                    lanes = ['baseline', 'candidate'] if repeat % 2 == 0 else ['candidate', 'baseline']
                    for lane in lanes:
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
        atomic_json(directory / 'paired-failure.json', {'measurements': rows})
        raise
    if any(digest(directory / name) != checksum for name, checksum in pins.items()):
        raise RuntimeError('artifact changed during measurements')
    summaries = []
    for lane in ['baseline', 'candidate']:
        for threads in [1, 2, 4]:
            subset = [row for row in rows if row['lane'] == lane and row['threads'] == threads]
            summaries.append({'lane': lane, 'threads': threads, 'depth_total': sum(row['depth'] for row in subset),
                              'nodes_total': sum(row['nodes'] for row in subset),
                              'timeouts': sum(row['timeout'] for row in subset),
                              'max_ms': max(row['milliseconds'] for row in subset)})
    atomic_json(output, {'version': 1, 'pins': pins, 'table_mib': 16, 'internal_ms': 230,
                        'external_ms': 250, 'roots': [{'category': r['category'], 'position': r['position']} for r in roots],
                        'measurements': rows, 'summaries': summaries})
    print(json.dumps(summaries))


if __name__ == '__main__':
    run(main)
