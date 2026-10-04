import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import torch

from genseki.rho.core import (Board, Guard, Network, Replay, StopWork, atomic, digest, encode,
                              load_model, play_game, promote, recover, save_model, search, train, write_json)


class RhoTests(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        torch.manual_seed(1)
        self.temp = tempfile.TemporaryDirectory(dir='Rho')
        self.root = Path(self.temp.name)
        self.model = Network().eval()
        self.guard = Guard(self.root, time.monotonic()+60)

    def tearDown(self):
        self.temp.cleanup()

    def test_encoding_translation_and_no_clipping(self):
        a = encode('G1|w|4|2|2|0,0=wQ;20,0=bQ')
        b = encode('G1|w|4|2|2|3,5=wQ;23,5=bQ')
        np.testing.assert_array_equal(a, b)
        self.assertNotEqual(a[1], 0)
        self.assertEqual(a.shape, (136,))

    def test_checkpoint_roundtrip_and_nonfinite_rejected(self):
        path = self.root/'rho.pt'
        save_model(path, self.model, {'generation': 0})
        loaded, meta = load_model(path)
        self.assertEqual(meta['generation'], 0)
        x = torch.randn(1, 136)
        c = torch.randn(7, 136)
        owners = torch.zeros(7, dtype=torch.long)
        for a, b in zip(self.model(x,c,owners), loaded(x,c,owners)):
            torch.testing.assert_close(a, b, rtol=0, atol=0)
        with torch.no_grad():
            next(self.model.parameters()).fill_(float('nan'))
        before = digest(path)
        with self.assertRaises(ValueError):
            save_model(path, self.model, {})
        self.assertEqual(digest(path), before)

    def test_variable_legal_policy_and_value_bounds(self):
        states = torch.randn(1, 136)
        children = torch.randn(13, 136)
        owners = torch.zeros(13, dtype=torch.long)
        logits, values = self.model(states, children, owners)
        self.assertEqual(logits.shape, (13,))
        self.assertAlmostEqual(logits.softmax(0).sum().item(), 1., places=6)
        self.assertLessEqual(abs(values.item()), 1.)
        reverse, _ = self.model(states, children.flip(0), owners)
        torch.testing.assert_close(reverse, logits.flip(0))

    def test_promotion_requires_complete_pass_and_recovery(self):
        baseline = self.root/'checkpoints'/'G0.pt'
        original = save_model(baseline, self.model, {'generation': 0})
        entry = dict(generation=0, checkpoint='checkpoints/G0.pt', sha256=original)
        state = dict(champion=entry, lineage=[entry])
        write_json(self.root/'state.json', state)
        write_json(self.root/'state.backup.json', state)
        atomic(self.root/'champion'/'rho.pt', baseline.read_bytes())
        candidate = self.root/'candidate.pt'
        save_model(candidate, self.model, {'generation': 1})
        self.assertFalse(promote(self.root, state, candidate, {'complete': False, 'score': 1}, .6))
        self.assertFalse(promote(self.root, state, candidate, {'complete': True, 'score': .5}, .6))
        self.assertEqual(original, digest(self.root/'champion'/'rho.pt'))
        atomic(self.root/'champion'/'rho.pt', b'broken')
        atomic(self.root/'state.json', b'{')
        atomic(self.root/'candidate.pt.tmp', b'partial')
        recover(self.root)
        self.assertEqual(original, digest(self.root/'champion'/'rho.pt'))
        self.assertFalse((self.root/'candidate.pt.tmp').exists())
        self.assertTrue(promote(self.root, state, candidate, {'complete': True, 'score': .75}, .6))
        self.assertEqual(state['champion']['generation'], 1)
        self.assertEqual(recover(self.root)['champion']['generation'], 1)

    def test_replay_capacity_hash_and_partial(self):
        replay = Replay(self.root/'replay', 3)
        replay.add([{'n': 1}, {'n': 2}], {'seed': 1})
        replay.add([{'n': 3}, {'n': 4}], {'seed': 2})
        self.assertEqual(replay.size, 2)
        self.assertEqual(len(list(replay.root.glob('*.gz'))), 1)
        self.assertEqual(replay.sample(1, 99), replay.sample(1, 99))
        atomic(replay.root/'orphan.gz', b'partial')
        restored = Replay(replay.root, 3)
        self.assertFalse((replay.root/'orphan.gz').exists())
        self.assertEqual(restored.sample(10, 1), [{'n': 3}, {'n': 4}])
        atomic(replay.root/restored.items[0]['file'], b'bad')
        with self.assertRaises(ValueError):
            Replay(replay.root, 3)

    def test_guards(self):
        with patch('genseki.rho.core.available_ram', return_value=1024**3-1):
            with self.assertRaises(StopWork):
                self.guard.check()
        with patch('genseki.rho.core.available_ram', return_value=int(1.9*1024**3)):
            with self.assertRaises(StopWork):
                self.guard.check()
        self.guard.deadline = time.monotonic()-1
        with self.assertRaises(StopWork):
            self.guard.check()

    def test_parallel_resource_guard(self):
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(lambda: [self.guard.check() for _ in range(30)]) for _ in range(2)]
            for future in futures:
                future.result()

    def test_disk_guard_stops_before_cap(self):
        with patch('genseki.rho.core.folder_bytes', return_value=self.guard.disk_cap-1):
            with self.assertRaises(StopWork):
                self.guard.check()

    def test_real_deadline_closes_native_worker(self):
        board = Board('build/genseki.exe', self.guard)
        self.guard.deadline = time.monotonic()+.03
        try:
            with self.assertRaises((StopWork, TimeoutError)):
                search(board, self.model, np.random.default_rng(1), 10000)
        finally:
            board.close()
        self.assertIsNotNone(board.native.process.poll())

    def test_training_oom_reduces_batch(self):
        config = {'simulations': 2, 'cpuct': 1.5, 'max_plies': 8, 'device': 'cpu',
                  'learning_rate': .001, 'batch_size': 4, 'epochs': 1}
        examples, _ = play_game('build/genseki.exe', {'w': self.model, 'b': self.model},
                                config, 1, self.guard)
        for example in examples:
            example['game_id'] = 'test-game'
        forward = self.model.forward
        calls = []
        def fail_once(*args):
            calls.append(1)
            if len(calls) == 1:
                raise torch.cuda.OutOfMemoryError('injected test failure')
            return forward(*args)
        with patch.object(self.model, 'forward', fail_once):
            metrics = train(self.model, examples, 'build/genseki.exe', config, self.guard, 1)
        self.assertEqual(metrics['effective_batch_size'], 2)
        self.assertEqual(metrics['history'][0]['optimizer_updates'], 4)

    def test_mcts_all_legal_visits_and_board_restored(self):
        board = Board('build/genseki.exe', self.guard)
        try:
            initial = board.game
            legal = board.children()
            moves, visits, children = search(board, self.model, np.random.default_rng(2), 9)
            self.assertEqual(moves, [m for m, _ in legal])
            self.assertEqual(sum(visits), 9)
            self.assertEqual(children, legal)
            self.assertEqual(board.game, initial)
            board.play(moves[int(np.argmax(visits))])
            self.assertEqual(board.terminal(), None)
        finally:
            board.close()

    def test_seeded_selfplay_and_cap_excluded_value(self):
        config = {'simulations': 2, 'cpuct': 1.5, 'max_plies': 8}
        first, game = play_game('build/genseki.exe', {'w': self.model, 'b': self.model}, config, 4, self.guard)
        second, other = play_game('build/genseki.exe', {'w': self.model, 'b': self.model}, config, 4, self.guard)
        self.assertEqual(first, second)
        self.assertEqual(game['moves'], other['moves'])
        self.assertTrue(all(e['z'] is None for e in first))

    def test_terminal_perspective(self):
        board = Board.__new__(Board)
        board.game = 'Base;WhiteWins;Black[8]'
        self.assertEqual(board.terminal(), -1)
        board.game = 'Base;BlackWins;White[8]'
        self.assertEqual(board.terminal(), -1)
        board.game = 'Base;WhiteWins;White[8]'
        self.assertEqual(board.terminal(), 1)
        board.game = 'Base;Draw;Black[8]'
        self.assertEqual(board.terminal(), 0)
        self.assertEqual(search(board, self.model, np.random.default_rng(1)), ([], [], []))

    def test_mcts_backup_prefers_immediate_win(self):
        class ToyBoard:
            # Explicit test-only tree: both leaves are terminal from opponent perspective.
            def __init__(self, guard):
                self.guard, self.move = guard, None
            def terminal(self):
                return {'win': -1., 'lose': 1., None: None}[self.move]
            def children(self):
                return [['win', 'G1|b|1|1|0|0,0=wA1'], ['lose', 'G1|b|1|1|0|0,0=wB1']]
            def position(self):
                return 'G1|w|0|0|0|'
            def play(self, move):
                self.move = move
            def undo(self):
                self.move = None
        toy = ToyBoard(self.guard)
        moves, counts, _ = search(toy, self.model, np.random.default_rng(2), 24)
        self.assertGreater(counts[moves.index('win')], counts[moves.index('lose')])
        self.assertEqual(sum(counts), 24)
        self.assertIsNone(toy.move)

    def test_campaign_timeout_preserves_champion_and_reports(self):
        from genseki.rho.campaign import DEFAULTS, run_campaign
        config = dict(DEFAULTS, hours=.001, workers=1, simulations=2, max_plies=8,
                      train_positions=8, arena_games=2, device='cpu')
        # Initialization is allowed; next guard check simulates an expired campaign.
        original = Guard.check
        calls = []
        def expire(guard):
            calls.append(1)
            if len(calls) > 1:
                raise StopWork('test deadline')
            return original(guard)
        with patch.object(Guard, 'check', expire):
            self.assertEqual(run_campaign(self.root, config, smoke=True), 0)
        result = json.loads((self.root/'reports'/'latest.json').read_text())
        self.assertEqual(result['status'], 'stopped')
        self.assertEqual(result['aborted_work'][0]['reason'], 'test deadline')
        state = recover(self.root)
        self.assertEqual(digest(self.root/'champion'/'rho.pt'), state['champion']['sha256'])

    def test_tiny_end_to_end_training_arena_reports(self):
        from genseki.rho.campaign import DEFAULTS, run_campaign
        config = dict(DEFAULTS, hours=.02, workers=1, simulations=2, max_plies=8,
                      train_positions=16, sample_positions=16, arena_games=2,
                      batch_size=2, epochs=1, device='cpu')
        self.assertEqual(run_campaign(self.root, config, smoke=True), 0)
        result = json.loads((self.root/'reports'/'latest.json').read_text())
        self.assertEqual(result['status'], 'smoke_complete')
        self.assertEqual(result['totals']['positions'], 16)
        self.assertTrue(result['attempts'][0]['arena']['complete'])
        self.assertTrue((self.root/'reports'/'latest.md').exists())
        champion, metadata = load_model(self.root/'champion'/'rho.pt')
        self.assertGreater(metadata['training']['history'][0]['optimizer_updates'], 0)

    def test_interrupted_arena_cannot_promote(self):
        from genseki.rho.campaign import DEFAULTS, run_campaign
        config = dict(DEFAULTS, hours=.02, workers=1, simulations=2, max_plies=8,
                      train_positions=16, sample_positions=16, arena_games=2,
                      batch_size=2, epochs=1, device='cpu')
        before = []
        def abort(*args):
            before.append(digest(self.root/'champion'/'rho.pt'))
            raise StopWork('test interrupted arena')
        with patch('genseki.rho.campaign.arena', abort):
            self.assertEqual(run_campaign(self.root, config, smoke=True), 0)
        state = recover(self.root)
        self.assertEqual(state['champion']['generation'], 0)
        self.assertEqual(digest(self.root/'champion'/'rho.pt'), before[0])
        self.assertEqual(state['attempts'][0]['status'], 'arena_pending')


if __name__ == '__main__':
    unittest.main()
