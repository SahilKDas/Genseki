from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import os
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path

import torch

from .core import (Guard, Network, Replay, StopWork, arena, atomic, digest, folder_bytes,
                   load_model, play_game, promote, recover, save_model, train, write_json)


DEFAULTS = dict(hours=8., workers=2, simulations=64, replay_positions=200000, max_plies=160,
                train_positions=5000, sample_positions=10000, epochs=2, batch_size=128,
                device='auto', cpuct=1.5, learning_rate=.001, arena_games=40,
                promotion_threshold=.6, seed=1701, disk_cap=2_000_000_000,
                engine='build/genseki_rules.exe', move_seconds=30.)


def persist(root, state):
    # Backup is also a valid complete transaction, never a partially written JSON file.
    write_json(root/'state.backup.json', state)
    write_json(root/'state.json', state)


def environment():
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip()
        dirty = subprocess.check_output(['git', 'status', '--porcelain'], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        commit, dirty = None, 'unknown'
    return dict(source_commit=commit, source_dirty=bool(dirty), python=sys.version,
                torch=str(torch.__version__), cuda=torch.version.cuda, platform=platform.platform(),
                cpu=platform.processor(), gpu=torch.cuda.get_device_name(0) if torch.cuda.is_available() else None,
                engine_sha256=None,
                source_files={str(p): digest(p) for p in Path('genseki/rho').glob('*.py')})


def report(root, state, run):
    run['champion'] = state['champion']
    run['lineage'] = state['lineage']
    run['attempts'] = state['attempts']
    run['totals'] = state['totals']
    try:
        run['replay_positions'] = Replay(root/'replay', run['config']['replay_positions'], cleanup=False).size
    except Exception as error:
        run['replay_positions'] = None
        run['replay_integrity_error'] = str(error)
    run['replay_bytes'] = folder_bytes(root/'replay')
    write_json(root/'reports'/f"{run['id']}.json", run)
    write_json(root/'reports'/'latest.json', run)
    text = (f"# Rho {run['label']} campaign\n\n"
            f"Status: {run['status']}. Elapsed: {run['elapsed_seconds']:.2f} seconds.\n\n"
            f"Champion: G{state['champion']['generation']} `{state['champion']['sha256']}`.\n\n"
            f"No external strength claim. Nokamute was not used for training or evaluated.\n\n"
            f"## Evidence\n\n```json\n{json.dumps(run, indent=2)}\n```\n")
    atomic(root/'reports'/'latest.md', text.encode())
    atomic(root/'reports'/f"{run['id']}.md", text.encode())


def run_campaign(root, config, smoke=False, resume=False):
    # Fail before acquiring a workspace lock when the rules binary is absent.
    engine_hash = digest(config['engine'])
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    for folder in ('champion', 'challenger', 'replay', 'checkpoints', 'reports', 'models', 'logs'):
        (root/folder).mkdir(exist_ok=True)
    # OS file lock releases automatically on crash/reboot; prevents concurrent Rho runners.
    lock = (root/'campaign.lock').open('a+b')
    lock.seek(0)
    lock.write(b'0')
    lock.flush()
    lock.seek(0)
    if os.name == 'nt':
        import msvcrt
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    started = time.monotonic()
    guard = Guard(root, started+config['hours']*3600, config['disk_cap'])
    torch.set_num_threads(1)
    if os.name == 'nt':
        import ctypes
        get_handle = ctypes.windll.kernel32.GetCurrentProcess
        get_handle.restype = ctypes.c_void_p
        set_priority = ctypes.windll.kernel32.SetPriorityClass
        set_priority.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        set_priority(get_handle(), 0x40)
    torch.manual_seed(config['seed'])
    run = dict(id=f"campaign-{time.time_ns()}", label='smoke' if smoke else 'development',
               config=config, command=sys.argv, environment=environment(), status='running',
               aborted_work=[], resources=guard.metrics)
    run['environment']['engine_sha256'] = engine_hash
    snapshot = {str(p): p.read_text(encoding='utf-8') for p in Path('genseki/rho').glob('*.py')}
    import gzip
    snapshot_path = root/'reports'/f"{run['id']}-source.json.gz"
    atomic(snapshot_path, gzip.compress(json.dumps(snapshot).encode()))
    run['source_snapshot'] = str(snapshot_path.relative_to(root))
    run['source_snapshot_sha256'] = digest(snapshot_path)
    state = None
    try:
        guard.check()
        if (root/'state.json').exists() or (root/'state.backup.json').exists():
            if not resume:
                raise ValueError('workspace already initialized: use --resume')
            state = recover(root)
            state['recoveries'].append({'phase': state['phase'], 'time': time.time()})
        else:
            model = Network()
            metadata = dict(generation=0, bootstrap='random initialization', seed=config['seed'],
                            architecture='legal-successor MLP v1', parameters=sum(p.numel() for p in model.parameters()))
            model_hash = save_model(root/'checkpoints'/'G0.pt', model, metadata)
            atomic(root/'champion'/'rho.pt', (root/'checkpoints'/'G0.pt').read_bytes())
            entry = dict(generation=0, sha256=model_hash, checkpoint='checkpoints/G0.pt')
            state = dict(champion=entry, lineage=[entry], attempts=[], next_generation=1,
                         phase='initialized', seed=config['seed'], recoveries=[],
                         totals=dict(selfplay_games=0, positions=0, natural_games=0, capped_games=0),
                         model=metadata, environment=run['environment'])
            persist(root, state)
        for attempt in state['attempts']:
            if attempt['status'] == 'arena_pending':
                attempt['status'] = 'aborted'
                attempt['reason'] = 'resume after interrupted arena; no promotion'
                write_json(root/'reports'/f"G{attempt['generation']}-aborted.json", attempt)
        if smoke:
            write_json(root/'smoke-config.json', config)
            write_json(root/'config.json', DEFAULTS)
        else:
            write_json(root/'config.json', config)
        replay = Replay(root/'replay', config['replay_positions'])
        while True:
            guard.check()
            generation = state['next_generation']
            state['next_generation'] += 1
            state['phase'] = 'selfplay'
            state['last_successful_operation'] = 'begin generation'
            persist(root, state)
            champion, _ = load_model(root/'champion'/'rho.pt')
            collected = 0
            while collected < config['train_positions']:
                guard.check()
                # Thread workers each own a C++ subprocess; shared read-only CPU model.
                # PyTorch has one heavy thread; no process pool copies of CUDA/runtime.
                with concurrent.futures.ThreadPoolExecutor(max_workers=config['workers']) as pool:
                    futures = [pool.submit(play_game, config['engine'], {'w': champion, 'b': champion},
                                           config, config['seed']+state['totals']['selfplay_games']+w,
                                           guard) for w in range(config['workers'])]
                    for future in futures:
                        examples, game = future.result()
                        game['generation'] = state['champion']['generation']
                        game['champion_sha256'] = state['champion']['sha256']
                        for example in examples:
                            example['game_id'] = str(game['seed'])
                        replay.add(examples, game)
                        collected += len(examples)
                        totals = state['totals']
                        totals['selfplay_games'] += 1
                        totals['positions'] += len(examples)
                        totals['natural_games'] += int(game['natural'])
                        totals['capped_games'] += int(not game['natural'])
                        persist(root, state)
                        print(f"self-play game {totals['selfplay_games']}: {len(examples)} positions, {game['reason']}", flush=True)
            state['phase'] = 'training'
            persist(root, state)
            samples = replay.sample(config['sample_positions'], config['seed']+generation)
            if not state.get('bootstrap_trained'):
                # Initial G0 construction includes a real self-play policy bootstrap.
                # Preserve the random precursor; all G1+ replacements still require an arena.
                bootstrap, _ = load_model(root/'champion'/'rho.pt')
                bootstrap_training = train(bootstrap, samples, config['engine'], config, guard, config['seed'])
                guard.check()
                bootstrap_path = root/'checkpoints'/'G0-trained.pt'
                bootstrap_hash = save_model(bootstrap_path, bootstrap,
                    dict(state['model'], bootstrap='self-play policy/value bootstrap',
                         training=bootstrap_training, replay_shards=replay.items))
                entry = dict(generation=0, sha256=bootstrap_hash, checkpoint='checkpoints/G0-trained.pt',
                             initialization=True, training=bootstrap_training)
                state['champion'] = entry
                state['lineage'].append(entry)
                state['bootstrap_trained'] = True
                persist(root, state)
                atomic(root/'champion'/'rho.pt', bootstrap_path.read_bytes())
                champion, _ = load_model(root/'champion'/'rho.pt')
            candidate, _ = load_model(root/'champion'/'rho.pt')
            training = train(candidate, samples, config['engine'], config, guard, config['seed']+generation)
            guard.check()
            candidate_path = root/'challenger'/'rho.pt'
            meta = dict(generation=generation, parent=state['champion'], training=training,
                        config=config, replay_shards=replay.items, seed=config['seed']+generation,
                        architecture=state['model']['architecture'], parameters=state['model']['parameters'])
            candidate_hash = save_model(candidate_path, candidate, meta)
            candidate, _ = load_model(candidate_path)
            state['phase'] = 'arena'
            attempt = dict(generation=generation, candidate_sha256=candidate_hash,
                           champion_sha256=state['champion']['sha256'], training=training,
                           config=config, status='arena_pending')
            state['attempts'].append(attempt)
            persist(root, state)
            write_json(root/'reports'/f'G{generation}-training.json', attempt)
            def arena_progress(records):
                write_json(root/'reports'/f'G{generation}-arena-progress.json',
                           dict(generation=generation, complete=False, games=records,
                                candidate_sha256=candidate_hash,
                                champion_sha256=state['champion']['sha256']))
                print(f"G{generation}: arena {len(records)}/{config['arena_games']}", flush=True)

            result = arena(config['engine'], champion, candidate, config, config['seed']+100000+generation,
                           guard, progress=arena_progress)
            attempt['arena'] = result
            guard.check()
            promoted = promote(root, state, candidate_path, result, config['promotion_threshold'])
            attempt['status'] = 'promoted' if promoted else 'rejected'
            state['phase'] = 'idle'
            state['last_successful_operation'] = 'completed arena'
            persist(root, state)
            write_json(root/'reports'/f'G{generation}-arena.json', attempt)
            print(f"G{generation}: score {result['score']:.3f}, {attempt['status']}", flush=True)
            if smoke:
                run['status'] = 'smoke_complete'
                break
    except (StopWork, KeyboardInterrupt, TimeoutError) as error:
        run['status'] = 'stopped'
        run['aborted_work'].append({'phase': state['phase'] if state else 'preflight', 'reason': str(error) or 'Ctrl+C'})
    except Exception as error:
        run['status'] = 'failed'
        run['aborted_work'].append({'phase': state['phase'] if state else 'preflight',
                                    'reason': str(error), 'traceback': traceback.format_exc()})
    finally:
        run['elapsed_seconds'] = time.monotonic()-started
        if state is not None:
            state['phase_at_stop'] = state['phase']
            state['phase'] = run['status']
            persist(root, state)
            report(root, state, run)
            run['resources']['peak_disk_bytes'] = max(run['resources']['peak_disk_bytes'], folder_bytes(root))
            run['workspace_bytes_at_exit'] = folder_bytes(root)
            run['resources']['native_process_count_at_exit'] = guard.process_count
            report(root, state, run)
        else:
            write_json(root/'reports'/f"{run['id']}.json", run)
        lock.close()
        print(json.dumps({'status': run['status'], 'elapsed_seconds': run['elapsed_seconds'],
                          'aborted_work': run['aborted_work']}, indent=2), flush=True)
    return 1 if run['status'] == 'failed' else 0


def main():
    parser = argparse.ArgumentParser(description='Bounded Rho policy/value campaign')
    parser.add_argument('--workspace', type=Path, default=Path('Rho'))
    parser.add_argument('--smoke-test', action='store_true')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    for key, value in DEFAULTS.items():
        parser.add_argument('--'+key.replace('_', '-'), type=type(value), default=None)
    args = parser.parse_args()
    config = dict(DEFAULTS)
    if args.resume and (args.workspace/'config.json').exists():
        config.update(json.loads((args.workspace/'config.json').read_text()))
    if config['engine'].replace('\\', '/') == 'build/genseki.exe':
        config['engine'] = 'build/genseki_rules.exe'
    if args.smoke_test:
        config.update(hours=.15, workers=1, simulations=4, max_plies=64, train_positions=128,
                      sample_positions=256, epochs=1, batch_size=8, arena_games=2, device='cpu')
    for key in DEFAULTS:
        if getattr(args, key) is not None:
            config[key] = getattr(args, key)
    if config['workers'] not in (1, 2) or config['arena_games'] < 2 or config['arena_games'] % 2:
        parser.error('workers must be 1 or 2; arena-games must be positive and even')
    for key in ('hours', 'simulations', 'replay_positions', 'max_plies', 'train_positions',
                'sample_positions', 'epochs', 'batch_size', 'cpuct', 'learning_rate', 'move_seconds'):
        if not math.isfinite(config[key]) or config[key] <= 0:
            parser.error(key+' must be positive')
    if config['disk_cap'] > 2_000_000_000 or config['disk_cap'] < 32_000_000:
        parser.error('disk cap must be between 32 MB and 2 GB')
    if not .5 < config['promotion_threshold'] <= 1:
        parser.error('promotion threshold must exceed .5 and be <=1')
    if config['device'] not in ('auto', 'cpu', 'cuda'):
        parser.error('device must be auto, cpu, or cuda')
    if args.dry_run:
        print(json.dumps(dict(config=config, model_parameters=sum(p.numel() for p in Network().parameters()),
                              notes='No training. Throughput must be measured on this machine.'), indent=2))
        return
    if os.name == 'nt' and not args.smoke_test:
        # Enforce the existing device contract for unattended normal runs.
        result = subprocess.run(['powershell', '-NoProfile', '-Command',
            "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^python' } | Select-Object -ExpandProperty CommandLine"],
            capture_output=True, text=True, timeout=10)
        if result.returncode:
            parser.error('cannot inspect active jobs; refusing unattended start')
        if any('gauntlet' in line.lower()
               for line in result.stdout.splitlines()):
            parser.error('active training/gauntlet detected; finish it before overnight training')
    raise SystemExit(run_campaign(args.workspace, config, args.smoke_test, args.resume))


if __name__ == '__main__':
    main()
