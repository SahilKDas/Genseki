"""Bounded mirrored UHP matches with the native GUI as a live spectator."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import ctypes
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import time

from .uhp import UhpProcess
from .artifacts import portable_value, verify_manifest
from .resources import HEAVY_PROCESS_PATTERNS, available_ram, heavy_job_path, team_job_path, job_lock

ROOT = Path(__file__).resolve().parents[1]
INITIAL = 'Base;NotStarted;White[1]'
SEARCH_DEPTH_LIMIT = 64
VALIDATION_POLICY = 'reconstructed-position-v1'


def atomic(path, text):
    path = Path(path)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_bytes(text.encode('utf-8'))
    # Windows readers can briefly hold the old snapshot open.
    for attempt in range(20):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(.01)


def save(path, value):
    atomic(path, json.dumps(portable_value(ROOT, value), indent=2) + '\n')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()


def windows_processes():
    script = ("$ErrorActionPreference='Stop'; @(Get-CimInstance Win32_Process | "
              "Select-Object ProcessId,Name,CommandLine) | ConvertTo-Json -Compress")
    result = subprocess.run(['powershell', '-NoProfile', '-Command', script],
                            capture_output=True, text=True, check=True, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    data = json.loads(result.stdout or '[]')
    return data if isinstance(data, list) else [data]


def preflight(gui):
    if os.name != 'nt':
        if gui:
            raise RuntimeError('the native spectator requires Windows; use --no-gui elsewhere')
        return
    processes = windows_processes()
    heavy = HEAVY_PROCESS_PATTERNS
    guis = controllers = 0
    for process in processes:
        if process['ProcessId'] == os.getpid():
            continue
        name = (process.get('Name') or '').lower()
        line = (process.get('CommandLine') or '').replace('\\', '/').lower()
        if name.startswith('python') and any(pattern in line for pattern in heavy):
            raise RuntimeError('another training or gauntlet job is running')
        guis += int('genseki_gui' in name or 'genseki_spectator' in name)
        controllers += int(name.startswith('python') and ('bridge' in line or 'match_controller' in line))
    if gui and guis >= 2:
        raise RuntimeError('two Genseki GUIs are already running')
    if controllers >= 2:
        raise RuntimeError('two match controllers are already running')


class StageStopped(RuntimeError):
    pass


class Guard:
    def __init__(self, hours, output):
        self.deadline = time.monotonic() + hours*3600
        self.output = output
        self.last_storage = -float('inf')

    def check(self):
        if time.monotonic() >= self.deadline:
            raise StageStopped('stage time limit reached')
        if os.name == 'nt':
            try:
                free_ram = available_ram()
            except OSError as error:
                raise StageStopped('cannot measure available RAM') from error
            if free_ram < 512*1024**2:
                raise StageStopped('available RAM below 0.5 GiB')
        if time.monotonic()-self.last_storage >= 60:
            paths = list(ROOT.glob('build*')) + list(ROOT.glob('cmake-build-*')) + [ROOT/p for p in (
                'Alpha/work', 'Nu/work', 'Iota/work', 'Lab/work', '.tmp', 'reports/work',
                'data/generated', 'models/work')]
            if not any(self.output == p or p in self.output.parents for p in paths):
                paths.append(self.output)
            total = sum(p.stat().st_size for folder in paths if folder.is_dir()
                        for p in folder.rglob('*') if p.is_file() and not p.is_symlink())
            if total + 128*1024**2 > 10_000_000_000:
                raise StageStopped('temporary storage would exceed 10 GB')
            if shutil.disk_usage(self.output).free < 512*1024**2:
                raise StageStopped('less than 0.5 GiB disk reserve')
            self.last_storage = time.monotonic()


def command(engine, text, guard, timeout=5):
    guard.check()
    remaining = guard.deadline-time.monotonic()
    try:
        lines, elapsed = engine.command(text, min(timeout, remaining))
    except TimeoutError:
        if time.monotonic() >= guard.deadline:
            raise StageStopped('stage time limit reached')
        raise
    if any(line.startswith(('err ', 'invalidmove')) for line in lines):
        raise RuntimeError(f'protocol/rules divergence: {text}: {lines}')
    return [line for line in lines if line != 'ok'], elapsed


def configure(engine, args, options, guard):
    requested = {}
    for option in options:
        name, separator, value = option.partition(' ')
        if not separator or not value:
            raise RuntimeError('engine option requires name and value')
        command(engine, 'options set '+option, guard)
        requested[name] = value
    offered, _ = command(engine, 'options', guard)
    names = {line.split(';')[0] for line in offered}
    thread = 'NumThreads' if 'NumThreads' in names else 'Threads'
    if thread not in names:
        raise RuntimeError('engine must expose NumThreads or Threads to enforce the CPU limit')
    command(engine, f'options set {thread} {args.threads}', guard)
    requested[thread] = str(args.threads)
    for name, value in [('BackgroundPondering', 'False'), ('RandomOpening', 'False'),
                        ('TableSizeMiB', str(args.table_mib)), ('TableMiB', str(args.table_mib))]:
        if name in names:
            command(engine, f'options set {name} {value}', guard)
            requested[name] = value
    effective, _ = command(engine, 'options', guard)
    parsed = {}
    for line in effective:
        fields = line.split(';')
        if len(fields) >= 3:
            parsed[fields[0]] = fields[2]
    for name, value in requested.items():
        if parsed.get(name, '').casefold() != value.casefold():
            raise RuntimeError('engine effective option mismatch: '+name)
    return dict(requested=requested,
                verified={name: parsed[name] for name in requested}, observed=parsed,
                evidence=effective)


def load_manifest(path, executable):
    with Path(path).open(encoding='utf-8') as stream:
        manifest = json.load(stream)
    # Frozen binaries stay comparable while the shared checkout evolves.
    # Source/build corroboration belongs to the pre-build doctor and retained log.
    issues = verify_manifest(ROOT, manifest, check_sources=False)
    if issues:
        raise RuntimeError('artifact manifest rejected: '+'; '.join(issues))
    artifact = manifest['artifacts']['executable']
    if (ROOT/artifact['path']).resolve() != Path(executable).resolve():
        raise RuntimeError('artifact manifest names a different executable')
    return manifest


class Spectator:
    def __init__(self, output, a, b, games):
        self.path = output/'live.txt'
        self.a, self.b, self.games = a, b, games
        self.game = INITIAL
        self.index = 0
        self.white, self.black = a, b
        self.points = 0
        self.completed = 0

    def publish(self, status, game=None):
        if game is not None:
            self.game = game
        lines = ['GENSEKI_SPECTATOR_V1', f'Genseki Gauntlet - {self.a} vs {self.b}',
                 f'Game {self.index+1}/{self.games}: {status}', self.white, self.black,
                 f'A {self.points:g} : B {self.completed-self.points:g} ({self.completed} finished)', self.game]
        atomic(self.path, '\n'.join(lines)+'\n')


def game_state(lines):
    states = [line for line in lines if line.startswith('Base;')]
    if len(states) != 1 or len(states[0].split(';')) < 3:
        raise RuntimeError(f'missing or malformed UHP game state: {lines}')
    return states[0]


def agreed_state(referee, states, guard):
    positions = []
    for state in states:
        lines, _ = command(referee, 'genseki-validate-game ' + state, guard)
        if len(lines) != 1 or not lines[0].startswith('G1|'):
            raise RuntimeError('referee did not reconstruct a position')
        positions.append(lines[0])
    if len(set(positions)) != 1 or len({tuple(s.split(';')[:3]) for s in states}) != 1:
        raise RuntimeError(f'protocol/rules divergence: {states}')
    return states[0]


def play_game(args, index, view, guard, factory=UhpProcess):
    frozen = {}
    for side in ('a', 'b'):
        path = getattr(args, side+'_manifest', None)
        if path:
            executable = args.engine_a if side == 'a' else args.engine_b
            frozen[side] = load_manifest(path, executable)
    a_white = index % 2 == 0
    seed = args.seed + index//2
    view.index = index
    view.white, view.black = (view.a, view.b) if a_white else (view.b, view.a)
    view.publish('starting', INITIAL)
    moves = []
    timings = []
    with ExitStack() as stack:
        engines = []
        for argv in ([str(args.engine_a), *args.a_arg], [str(args.engine_b), *args.b_arg], [str(args.referee)]):
            guard.check()
            engine = factory(argv)
            stack.callback(engine.close)
            engines.append(engine)
        a, b, referee = engines
        settings = dict(a=configure(a, args, args.a_option, guard),
                        b=configure(b, args, args.b_option, guard))
        for side in ('a', 'b'):
            if side in frozen:
                expected = frozen[side]['effective_settings']['verified']
                actual = settings[side]['observed']
                if any(str(actual.get(k, '')).casefold() != str(v).casefold()
                       for k, v in expected.items()):
                    raise RuntimeError('effective settings differ from frozen manifest')
        states = [game_state(command(engine, 'newgame Base', guard)[0]) for engine in engines]
        state = agreed_state(referee, states, guard)
        rng = random.Random(seed)
        while len(moves) < args.cap:
            white = state.split(';')[2].startswith('White[')
            actor = a if white == a_white else b
            side = 'A' if actor is a else 'B'
            if len(moves) < 4:
                legal, _ = command(referee, 'validmoves', guard)
                if not legal or not legal[0]:
                    raise RuntimeError('referee supplied no opening moves')
                move = rng.choice(sorted(legal[0].split(';')))
            else:
                view.publish(f'{side} thinking, ply {len(moves)+1}')
                try:
                    response, elapsed = command(actor,
                        f'bestmove depthorseconds {SEARCH_DEPTH_LIMIT} {args.internal_ms/1000:.3f}',
                        guard, args.external_ms/1000)
                    if elapsed*1000 > args.external_ms:
                        raise TimeoutError('external move deadline')
                except TimeoutError:
                    return dict(index=index, seed=seed, a_color='white' if a_white else 'black',
                                score=float(actor is b), termination='timeout', loser=side,
                                game=state, moves=moves, move_ms=timings, effective_settings=settings)
                if not response:
                    raise RuntimeError('engine supplied no best move')
                move = response[0]
                timings.append(dict(ply=len(moves)+1, actor=side, milliseconds=elapsed*1000))
            states = [game_state(command(engine, 'play '+move, guard)[0]) for engine in (referee, a, b)]
            state = agreed_state(referee, states, guard)
            moves.append(move)
            view.publish(f'ply {len(moves)}: {move}', state)
            result = state.split(';')[1]
            if result in ('WhiteWins', 'BlackWins', 'Draw'):
                score = .5 if result == 'Draw' else float((result == 'WhiteWins') == a_white)
                return dict(index=index, seed=seed, a_color='white' if a_white else 'black',
                            score=score, termination='natural', result=result,
                            game=state, moves=moves, move_ms=timings, effective_settings=settings)
            if result != 'InProgress':
                raise RuntimeError(f'unexpected game result: {result}')
            # Optional pacing affects viewing only, never the measured search time.
            if args.move_delay_ms:
                time.sleep(min(args.move_delay_ms/1000, max(0, guard.deadline-time.monotonic())))
        return dict(index=index, seed=seed, a_color='white' if a_white else 'black',
                    score=.5, termination='ply_cap', game=state, moves=moves, move_ms=timings,
                    effective_settings=settings)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--engine-a', type=Path, default=ROOT/'build/genseki.exe')
    p.add_argument('--engine-b', type=Path, required=True)
    p.add_argument('--a-arg', action='append', default=[], help='engine argument; use --a-arg=--model for flags')
    p.add_argument('--b-arg', action='append', default=[])
    p.add_argument('--a-option', action='append', default=[], help='UHP option, e.g. "Evaluator neural"')
    p.add_argument('--b-option', action='append', default=[])
    p.add_argument('--a-manifest', type=Path, help='frozen artifact/settings manifest')
    p.add_argument('--b-manifest', type=Path, help='frozen artifact/settings manifest')
    p.add_argument('--name-a', default='Genseki')
    p.add_argument('--name-b', default='Opponent')
    p.add_argument('--referee', type=Path, default=ROOT/'build/genseki_rules.exe')
    p.add_argument('--gui', type=Path, default=ROOT/'build/genseki_spectator.exe')
    p.add_argument('--no-gui', action='store_true')
    p.add_argument('--output', type=Path, default=ROOT/'reports/work'/f'gauntlet-{time.time_ns()}')
    p.add_argument('--games', type=int, default=20)
    p.add_argument('--seed', type=int, default=71000)
    p.add_argument('--threads', type=int, default=1)
    p.add_argument('--table-mib', type=int, default=16)
    p.add_argument('--internal-ms', type=int, default=230)
    p.add_argument('--external-ms', type=int, default=250)
    p.add_argument('--cap', type=int, default=160)
    p.add_argument('--hours', type=float, default=2)
    p.add_argument('--move-delay-ms', type=int, default=0)
    return p


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if not (0 < args.games <= 1000 and args.games % 2 == 0 and 1 <= args.threads <= 12
            and 1 <= args.table_mib <= 256 and 4 <= args.cap <= 256 and 0 < args.hours <= 2
            and 0 < args.internal_ms < args.external_ms <= 60_000 and 0 <= args.move_delay_ms <= 5000):
        p.error('invalid bounds: even games 2..1000, threads 1..12, cap 4..256, hours (0,2], internal < external')
    for text in [args.name_a, args.name_b, *args.a_arg, *args.b_arg, *args.a_option, *args.b_option]:
        if '\n' in text or '\r' in text:
            p.error('names, arguments and options must be single lines')
    for key in ('engine_a', 'engine_b', 'referee', 'gui', 'output'):
        setattr(args, key, getattr(args, key).resolve())
    for binary in [args.engine_a, args.engine_b, args.referee] + ([] if args.no_gui else [args.gui]):
        if not binary.is_file():
            p.error(f'missing executable: {binary}; build genseki_spectator and genseki_rules first')
    args.output.mkdir(parents=True, exist_ok=False)
    view = Spectator(args.output, args.name_a, args.name_b, args.games)
    report = dict(kind='development', status='starting',
                  engine_a_sha256=digest(args.engine_a), engine_b_sha256=digest(args.engine_b),
                  referee_sha256=digest(args.referee), games=[], points=0)
    report['settings'] = portable_value(ROOT, vars(args))
    report['settings'].update(search_depth_limit=SEARCH_DEPTH_LIMIT, validation_policy=VALIDATION_POLICY)
    opening_plan = dict(generator='sorted-legal-random-four-plies-v1',
                        seeds=[args.seed+i for i in range(args.games//2)])
    report['opening_plan'] = opening_plan
    report['opening_plan_sha256'] = hashlib.sha256(
        json.dumps(opening_plan, sort_keys=True).encode('utf-8')).hexdigest()
    report['provenance_status'] = 'unverified-imports'
    guard = Guard(args.hours, args.output)
    gui = None
    try:
        with job_lock(team_job_path(ROOT)), job_lock(heavy_job_path(ROOT)), job_lock(ROOT/'reports/work/gauntlet.lock'):
            preflight(not args.no_gui)
            guard.check()
            manifests = {}
            for side, executable in (('a', args.engine_a), ('b', args.engine_b)):
                path = getattr(args, side+'_manifest')
                if path:
                    manifests[side] = load_manifest(path, executable)
            report['manifests'] = manifests
            if len(manifests) == 2:
                report['provenance_status'] = 'manifest-verified'
            if os.name == 'nt':
                kernel = ctypes.windll.kernel32
                kernel.GetCurrentProcess.restype = ctypes.c_void_p
                kernel.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
                kernel.SetPriorityClass(kernel.GetCurrentProcess(), 0x40)
            view.publish('waiting for engines')
            if not args.no_gui:
                # A visible native window; closing it does not interrupt the match.
                gui = subprocess.Popen([str(args.gui), '--spectate', str(view.path)],
                                       creationflags=subprocess.NORMAL_PRIORITY_CLASS if os.name == 'nt' else 0)
            report['status'] = 'running'
            save(args.output/'report.json', report)
            print(f'Live view: {view.path}\nEvidence: {args.output}', flush=True)
            for index in range(args.games):
                guard.check()
                for path, key in ((args.engine_a, 'engine_a_sha256'),
                                  (args.engine_b, 'engine_b_sha256'),
                                  (args.referee, 'referee_sha256')):
                    if digest(path) != report[key]:
                        raise RuntimeError('frozen executable changed during match')
                row = play_game(args, index, view, guard)
                save(args.output/f'game-{index+1:04d}.json', row)
                report['games'].append(row)
                report['points'] += row['score']
                view.points, view.completed = report['points'], len(report['games'])
                view.publish(f"{row['termination']}; A scored {row['score']:g}")
                save(args.output/'report.json', report)
                print(f"{index+1}/{args.games}: {row['termination']}; A {view.points:g} : B {view.completed-view.points:g}", flush=True)
            report['status'] = 'completed'
    except (KeyboardInterrupt, StageStopped) as error:
        report.update(status='stopped', error=str(error) or 'Ctrl+C')
    except Exception as error:
        report.update(status='rejected', error=portable_value(ROOT, str(error)))
    finally:
        report['last_game'] = view.game
        save(args.output/'report.json', report)
        view.publish(report['status'] + (': '+report['error'] if 'error' in report else ''))
    if report['status'] != 'completed':
        print(f"{report['status']}: {report.get('error', '')}", flush=True)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
