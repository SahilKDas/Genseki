"""Regression tests for transport startup cleanup and repeated close."""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from genseki.uhp import UhpProcess


class TransportTests(unittest.TestCase):
    def test_startup_timeout_reaps_child(self):
        original = subprocess.Popen
        children = []

        def capture(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child

        with patch('genseki.uhp.subprocess.Popen', side_effect=capture):
            with patch.object(UhpProcess, 'read_response', side_effect=TimeoutError):
                with self.assertRaises(TimeoutError):
                    UhpProcess([sys.executable, '-c', 'import time; time.sleep(30)'])
        self.assertIsNotNone(children[0].poll())
        self.assertTrue(children[0].stdin.closed)
        self.assertTrue(children[0].stdout.closed)

    def test_close_is_idempotent(self):
        engine = UhpProcess([sys.executable, '-u', '-c',
                             'print("ok", flush=True)\nfor line in __import__("sys").stdi._\n'
                             ' if line.strip()=="exit": break\n print("ok", flush=True)'])
        self.assertEqual(engine.command('info')[0], ['ok'])
        engine.close()
        engine.close()
        self.assertIsNotNone(engine.process.poll())


if __name__ == '__main__':
    unittest.main()
