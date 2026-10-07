"""Sequential asymmetric-budget development matches, without promotion."""
import json
import argparse
import time
from pathlib import Path

import numpy as np
import torch

from genseki.rho.core import Board, Guard, StopWork, digest, load_model, search, write_json
from genseki.uhp import UhpProcess


def command(engine, text, timeout=5):
    lines, elapsed = engine.command(text, timeout)
    if any(line.startswith(('err ', 'invalidmove ')) for line in lines):
        raise ValueError('Alpha protocol error')
    return lines[:-1], elapsed


def main():
    root = Path('Rho')
    output = root / 'reports/alpha-g1-matches.json'
    parser = argparse.ArgumentParser()
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    if output.exists() and not args.resume:
        raise ValueError('Refusing to overwrite evidence')
    state = json.loads((root / 'state.json').read_text())
    attempt = next(a for a in state['attempts'] if a['generation'] == 11)
    alpha_path = Path('Alpha/work/gen2/gen1.exe')
    models = [('G11', root / 'challenger/rho.pt', attempt['candidate_sha256']),
              ('G0', root / state['champion']['checkpoint'], state['champion']['sha256'])]
    deadline = Path('Rho/logs/alpha-g1-matches.stdout.log').stat().st_ctime + 8 * 3600
    remaining = deadline - time.time()
    if remaining <= 0:
        raise StopWork('Original match deadline expired')
    guard = Guard(root.resolve(), time.monotonic() + remaining, 2_000_000_000)
    guard.check()
    torch.set_num_threads(1)
    report = dict(complete=False, alpha_sha256=digest(alpha_path),
                  rules_sha256=digest('build/genseki_rules.exe'),
                  simulations=64, alpha_internal_ms=230, alpha_external_ms=250,
                  alpha_threads=1, max_plies=160, seed=301712,
                  asymmetric_budgets=True, games=[])
    if args.resume:
        previous = json.loads(output.read_text())
        for key in ('alpha_sha256', 'rules_sha256', 'simulations', 'alpha_internal_ms',
                    'alpha_external_ms', 'alpha_threads', 'max_plies', 'seed'):
            if previous[key] != report[key]:
                raise ValueError('Resume configuration mismatch: ' + key)
        if previous.get('complete') or previous.get('failure_kind') != 'StopWork':
            raise ValueError('Resume requires an incomplete resource/deadline stop')
        identities = [(g['model'], g['seed'], g['rho_color']) for g in previous['games']]
        if len(identities) != len(set(identities)):
            raise ValueError('Duplicate saved game')
        expected_hashes = {name: expected for name, _, expected in models}
        if any(not g['complete'] or g['model_sha256'] != expected_hashes[g['model']]
               for g in previous['games']):
            raise ValueError('Invalid saved game identity')
        write_json(root / 'reports' / f'alpha-g1-matches-before-resume-{time.time_ns()}.json', previous)
        report = previous
        report.setdefault('interruptions', []).append(dict(
            failure_kind=report.pop('failure_kind'),
            incomplete_game=report.pop('incomplete_game', None), resumed_at=time.time()))
    write_json(output, report)
    try:
        for name, path, expected in models:
            assert digest(path) == expected
            model, _ = load_model(path)
            for pair in range(10):
                seed = report['seed'] + pair
                for color in ('w', 'b'):
                    if any(g['model'] == name and g['seed'] == seed and g['rho_color'] == color
                           for g in report['games']):
                        continue
                    guard.check()
                    board = Board('build/genseki_rules.exe', guard)
                    alpha = None
                    record = dict(model=name, model_sha256=expected, seed=seed,
                                  rho_color=color, moves=[], timings=[], complete=False)
                    try:
                        alpha = UhpProcess([str(alpha_path.resolve())])
                        for option in ('NumThreads 1', 'TableSizeMiB 32',
                                       'RandomOpening False', 'BackgroundPondering False'):
                            command(alpha, 'options set ' + option)
                        command(alpha, 'newgame Base')
                        rng = np.random.default_rng(seed)
                        for _ in range(4):
                            legal = board.children()
                            move = legal[int(rng.integers(len(legal)))][0]
                            board.play(move)
                            command(alpha, 'pass' if move == 'pass' else 'play ' + move)
                            record['moves'].append(move)
                        reason, winner = 'ply_cap', None
                        for _ in range(4, 160):
                            guard.check()
                            result = board.terminal()
                            if result is not None:
                                reason = 'terminal'
                                winner = None if result == 0 else (board.side if result == 1 else
                                         ('b' if board.side == 'w' else 'w'))
                                break
                            side = board.side
                            started = time.monotonic()
                            if side == color:
                                board.operation_deadline = min(guard.deadline, started + 120)
                                legal, visits, _ = search(board, model, rng, 64, 1.5, False)
                                board.operation_deadline = guard.deadline
                                move = legal[int(np.argmax(visits))]
                            else:
                                try:
                                    lines, elapsed = command(alpha, 'bestmove depthorseconds 99 0.230', .250)
                                except TimeoutError:
                                    reason, winner = 'alpha_timeout', color
                                    break
                                if elapsed > .250:
                                    reason, winner = 'alpha_timeout', color
                                    break
                                move = next(line for line in lines if not line.startswith('info '))
                            record['timings'].append(dict(side=side, seconds=time.monotonic()-started))
                            board.play(move)
                            response, _ = command(alpha, 'pass' if move == 'pass' else 'play ' + move)
                            if not response or response[0].split(';')[1] != board.game.split(';')[1]:
                                raise ValueError('rules/result divergence')
                            record['moves'].append(move)
                        else:
                            result = board.terminal()
                            if result is not None:
                                reason = 'terminal'
                                winner = None if result == 0 else (board.side if result == 1 else
                                         ('b' if board.side == 'w' else 'w'))
                        record.update(complete=True, reason=reason, winner=winner,
                                      score=.5 if winner is None else float(winner == color))
                        report['games'].append(record)
                        write_json(output, report)
                        print(f"{name}: {sum(g['model']==name for g in report['games'])}/20 {reason}", flush=True)
                    except BaseException as error:
                        report['incomplete_game'] = record
                        report['failure_kind'] = type(error).__name__
                        raise
                    finally:
                        if alpha is not None:
                            alpha.close()
                        board.close()
        report['complete'] = True
    finally:
        report['resources'] = guard.metrics
        write_json(output, report)


if __name__ == '__main__':
    main()
