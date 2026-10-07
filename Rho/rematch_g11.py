"""Bounded independent G11 development rematch; never promotes a model."""
import json
import msvcrt
import time
from pathlib import Path

import torch

from genseki.rho.core import Guard, arena, digest, load_model, write_json


def main():
    root = Path('Rho')
    with (root / 'campaign.lock').open('r+b') as lock:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        state = json.loads((root / 'state.json').read_text())
        attempt = next(a for a in state['attempts'] if a['generation'] == 11)
        candidate_path = root / 'challenger/rho.pt'
        champion_path = root / state['champion']['checkpoint']
        assert digest(candidate_path) == attempt['candidate_sha256']
        assert digest(champion_path) == attempt['champion_sha256']
        torch.set_num_threads(1)
        guard = Guard(root.resolve(), time.monotonic() + 8 * 3600, 2_000_000_000)
        guard.check()
        champion, _ = load_model(champion_path)
        candidate, metadata = load_model(candidate_path)
        assert metadata['generation'] == 11
        config = dict(attempt['config'], arena_games=40, device='cpu')
        report = dict(complete=False, purpose='independent development replication',
                      seed=201712, config=config,
                      candidate_sha256=digest(candidate_path),
                      champion_sha256=digest(champion_path),
                      engine_sha256=digest(config['engine']), games=[])
        path = root / 'reports/G11-rematch.json'
        if path.exists():
            raise ValueError('Refusing to overwrite rematch evidence')
        write_json(path, report)

        def progress(records):
            report['games'] = records
            write_json(path, report)
            print(f"G11 rematch: {len(records)}/40", flush=True)

        try:
            report.update(arena(config['engine'], champion, candidate, config,
                                report['seed'], guard, progress))
        finally:
            report['resources'] = guard.metrics
            write_json(path, report)
        print(json.dumps({k: report[k] for k in
                          ('wins', 'losses', 'draws', 'score', 'complete')}), flush=True)


if __name__ == '__main__':
    main()
