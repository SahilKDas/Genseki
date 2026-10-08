"""Gauntlet orchestration tests using deterministic UHP peers, no search jobs."""
from pathlib import Path
import sys
import json
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from genseki import gauntlet as g


class Peer:
    instances = []
    timeout = False
    diverge = False
    fail_start = False
    replay_diverge = False

    def __init__(self, argv):
        if self.fail_start and argv[0] == 'b':
            raise RuntimeError('startup failed')
        self.name = argv[0]
        self.moves = []
        self.closed = False
        self.commands = []
        self.options = {'NumThreads': '1', 'BackgroundPondering': 'False', 'Evaluator': 'gen1'}
        self.instances.append(self)

    def command(self, text, timeout=5):
        self.commands.append(text)
        if text == 'options':
            return [f'NumThreads;int;{self.options["NumThreads"]};1;1;12',
                    f'BackgroundPondering;bool;{self.options["BackgroundPondering"]};False',
                    f'Evaluator;string;{self.options["Evaluator"]};gen1;gen1;neural', 'ok'], 0
        if text.startswith('options '):
            _, _, name, value = text.split(' ', 3)
            self.options[name] = value
            return ['ok'], 0
        if text == 'newgame Base':
            return [g.INITIAL, 'ok'], 0
        if text == 'validmoves':
            return ['wA1;wG1', 'ok'], 0
        if text.startswith('genseki-validate-game '):
            return ['G1|'+text.split(' ', 1)[1], 'ok'], 0
        if text.startswith('bestmove'):
            assert text.split()[2] == '64'
            if self.timeout and self.name == 'a':
                raise TimeoutError
            return ['wQ', 'ok'], .001
        if text.startswith('play '):
            self.moves.append(text[5:])
            result = 'WhiteWins' if self.diverge and self.name == 'b' else 'InProgress'
            side = 'White' if len(self.moves) % 2 == 0 else 'Black'
            replay = list(self.moves)
            if self.replay_diverge and self.name == 'b':replay[-1] = 'bA3'
            return [f'Base;{result};{side}[{len(self.moves)//2+1}];'+ ';'.join(replay), 'ok'], 0
        raise AssertionError(text)

    def close(self):
        self.closed = True


class GauntletTests(unittest.TestCase):
    def setUp(self):
        Peer.instances = []
        Peer.timeout = Peer.diverge = Peer.fail_start = Peer.replay_diverge = False
        self.temp = tempfile.TemporaryDirectory(dir=g.ROOT/'Lab')
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        self.args = g.parser().parse_args(['--engine-a', 'a', '--engine-b', 'b', '--referee', 'r', '--games', '2', '--cap', '6', '--no-gui'])
        self.view = g.Spectator(self.output, 'A', 'B', 2)
        self.guard = g.Guard(1, self.output)
        self.guard.check = lambda: None

    def test_mirrored_opening_and_cap(self):
        first = g.play_game(self.args, 0, self.view, self.guard, Peer)
        second = g.play_game(self.args, 1, self.view, self.guard, Peer)
        self.assertEqual(first['moves'][:4], second['moves'][:4])
        self.assertEqual((first['a_color'], second['a_color']), ('white', 'black'))
        self.assertEqual(first['score'], .5)
        self.assertEqual(first['termination'], 'ply_cap')
        self.assertTrue(all(p.closed for p in Peer.instances))
        lines = self.view.path.read_text().splitlines()
        self.assertNotIn(b'\r', self.view.path.read_bytes())
        self.assertEqual(len(lines), 7)
        self.assertEqual(lines[0], 'GENSEKI_SPECTATOR_V1')
        self.assertEqual(lines[3:5], ['B', 'A'])
        self.assertEqual(lines[6], second['game'])

    def test_timeout_is_forfeit_without_playing_stale_reply(self):
        Peer.timeout = True
        row = g.play_game(self.args, 0, self.view, self.guard, Peer)
        self.assertEqual(row['termination'], 'timeout')
        self.assertEqual(row['score'], 0)
        self.assertEqual(len(row['moves']), 4)
        self.assertTrue(all(p.closed for p in Peer.instances))

    def test_divergence_invalidates_match_and_reaps_engines(self):
        Peer.diverge = True
        with self.assertRaisesRegex(RuntimeError, 'divergence'):
            g.play_game(self.args, 0, self.view, self.guard, Peer)
        self.assertTrue(all(p.closed for p in Peer.instances))

    def test_partial_startup_reaps_existing_peer(self):
        Peer.fail_start = True
        with self.assertRaisesRegex(RuntimeError, 'startup'):
            g.play_game(self.args, 0, self.view, self.guard, Peer)
        self.assertEqual(len(Peer.instances), 1)
        self.assertTrue(Peer.instances[0].closed)

    def test_same_header_different_replay_is_rejected(self):
        Peer.replay_diverge = True
        with self.assertRaisesRegex(RuntimeError, 'divergence'):
            g.play_game(self.args, 0, self.view, self.guard, Peer)
        self.assertTrue(all(p.closed for p in Peer.instances))

    def test_guard_deadline_does_not_score_a_forfeit(self):
        self.guard.deadline = 0
        self.guard.check = g.Guard.check.__get__(self.guard)
        with self.assertRaises(g.StageStopped):
            g.play_game(self.args, 0, self.view, self.guard, Peer)

    def test_options_cannot_override_thread_and_pondering_limits(self):
        peer = Peer(['a'])
        g.configure(peer, self.args, ['NumThreads 99', 'BackgroundPondering True'], self.guard)
        self.assertEqual(peer.commands[-3:], ['options set NumThreads 1',
                         'options set BackgroundPondering False', 'options'])

    def test_ignored_options_are_rejected(self):
        peer = Peer(['a'])
        original = peer.command
        def ignores(text, timeout=5):
            if text == 'options set NumThreads 2':
                return ['ok'], 0
            return original(text, timeout)
        peer.command = ignores
        self.args.threads = 2
        with self.assertRaisesRegex(RuntimeError, 'effective option mismatch'):
            g.configure(peer, self.args, [], self.guard)

    def test_manifest_mismatch_rejects_before_starting_peers(self):
        path = self.output/'bad-manifest.json'
        path.write_text(json.dumps({'schema_version': 999}), encoding='utf-8')
        self.args.a_manifest = path
        with self.assertRaisesRegex(RuntimeError, 'manifest rejected'):
            g.play_game(self.args, 0, self.view, self.guard, Peer)
        self.assertEqual(Peer.instances, [])

    def test_saved_metadata_has_no_host_paths(self):
        path = self.output/'report.json'
        g.save(path, {'engine': g.ROOT/'build/engine.exe',
                      'error': 'C:/Users/private/weights.nnue unavailable'})
        value = json.loads(path.read_text())
        self.assertEqual(value['engine'], 'build/engine.exe')
        self.assertNotIn('Users', value['error'])

    def test_manifest_checks_observed_default_options(self):
        self.args.a_manifest = self.output/'frozen-manifest.json'
        manifest = {'effective_settings': {'verified': {'Evaluator': 'gen1'}}}
        with patch.object(g, 'load_manifest', return_value=manifest):
            row = g.play_game(self.args, 0, self.view, self.guard, Peer)
        self.assertEqual(row['effective_settings']['a']['observed']['Evaluator'], 'gen1')
        self.assertNotIn('Evaluator', row['effective_settings']['a']['requested'])


if __name__ == '__main__':
    unittest.main()
