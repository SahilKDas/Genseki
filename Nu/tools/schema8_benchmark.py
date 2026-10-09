"""Freeze schema-7/8 artifacts, consume component costs, and alternate timed UHP searches."""
import argparse
from contextlib import closing
import json
from pathlib import Path
import shutil
import struct
import subprocess

from benchmark import working_set
from evidence import atomic_json, digest
from research_job import run
from train import resource_guard, response
from genseki.uhp import UhpProcess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--benchmark', type=Path, required=True)
    parser.add_argument('--schema7', type=Path, required=True)
    parser.add_argument('--schema8', type=Path, required=True)
    parser.add_argument('--directory', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.directory.exists() or args.report.exists():
        raise RuntimeError('use new immutable experiment paths')
    resource_guard()
    seven, eight = args.schema7.read_bytes(), args.schema8.read_bytes()
    if struct.unpack_from('<I', seven, 8)[0] != 7 or struct.unpack_from('<I', eight, 8)[0] != 8 or seven[:8] != eight[:8] or seven[12:] != eight[12:]:
        raise RuntimeError('models do not preserve the exact schema-7 payload')
    provenance = json.loads(args.schema8.with_suffix('.provenance.json').read_text())
    if provenance['source_sha256'] != digest(args.schema7) or provenance['model_sha256'] != digest(args.schema8):
        raise RuntimeError('conversion provenance mismatch')
    args.directory.mkdir(parents=True)
    sources = {'engine.exe': args.engine, 'components.exe': args.benchmark,
               'schema7.nnue': args.schema7, 'schema8.nnue': args.schema8}
    pins = {}
    for name, source in sources.items():
        destination = args.directory / name
        shutil.copy2(source, destination); pins[name] = digest(destination)
    native = {}
    rows = []
    try:
        for schema in [7, 8]:
            resource_guard()
            result = subprocess.run([str((args.directory/'components.exe').resolve()),
                                     str((args.directory/f'schema{schema}.nnue').resolve())],
                                    text=True, capture_output=True, timeout=180)
            if result.returncode:
                raise RuntimeError('native component benchmark failed')
            native[str(schema)] = json.loads(result.stdout)
        roots = native['7']['components']
        if [r['position'] for r in roots] != [r['position'] for r in native['8']['components']]:
            raise RuntimeError('component roots differ')
        for repeat in range(3):
            for threads in [1, 8]:
                for root in roots:
                    for schema in ([7, 8] if repeat % 2 == 0 else [8, 7]):
                        resource_guard()
                        with closing(UhpProcess([str((args.directory/'engine.exe').resolve()),
                                                 '--model', str((args.directory/f'schema{schema}.nnue').resolve())])) as engine:
                            defaults = response(engine, 'options get Threads')[0]
                            expected = 8 if schema == 8 else 1
                            if defaults != f'Threads;int;{expected};{expected};1;12':
                                raise RuntimeError('schema thread default mismatch')
                            response(engine, f'options Threads {threads}')
                            response(engine, 'options TableMiB 16')
                            response(engine, 'options Profile True')
                            response(engine, 'nu-loadposition '+root['position'])
                            legal = response(engine, 'validmoves')[0].split(';')
                            row = {'schema': schema, 'threads': threads, 'repeat': repeat, 'category': root['category']}
                            try:
                                lines, elapsed = engine.command('bestmove depthorseconds 64 .23', .25)
                            except TimeoutError:
                                rows.append({**row, 'timeout': True, 'depth': 0, 'nodes': 0})
                                continue
                            if not lines or lines[0] not in legal:
                                raise RuntimeError('illegal timed reply')
                            info = response(engine, 'nu-searchinfo')[0].split()
                            profile = response(engine, 'nu-profile')[0].split()
                            memory = working_set(engine.process.pid)
                            if memory and max(memory['peak_working_set_bytes'], memory['peak_committed_bytes']) > 64*1024**2:
                                raise RuntimeError('common 64 MiB memory ceiling exceeded')
                            rows.append({**row, 'timeout': elapsed > .25, 'milliseconds': elapsed*1000,
                                         'depth': int(info[1]), 'nodes': int(info[3]), 'score': int(info[5]),
                                         'legal': True, 'profile': dict(zip(profile[::2], map(int, profile[1::2]))), 'memory': memory})
    except BaseException as error:
        atomic_json(args.directory/'failure.json', {'pins': pins, 'native': native, 'measurements': rows,
                                                    'failure_type': type(error).__name__})
        raise
    if any(digest(args.directory/name) != pin for name, pin in pins.items()):
        raise RuntimeError('frozen artifact changed')
    summaries = []
    for schema in [7, 8]:
        for threads in [1, 8]:
            subset = [row for row in rows if row['schema'] == schema and row['threads'] == threads]
            summaries.append({'schema': schema, 'threads': threads,
                              'depth_total': sum(r['depth'] for r in subset), 'nodes_total': sum(r['nodes'] for r in subset),
                              'timeouts': sum(r['timeout'] for r in subset)})
    report = {'version': 1, 'pins': pins, 'provenance': provenance, 'native': native,
              'measurements': rows, 'summaries': summaries, 'internal_ms': 230, 'external_ms': 250,
              'table_mib': 16, 'memory_ceiling_bytes': 64*1024**2, 'promoted': False}
    atomic_json(args.directory/'results.json', report)
    atomic_json(args.report, report)
    print(json.dumps(summaries))


if __name__ == '__main__':
    run(main)
