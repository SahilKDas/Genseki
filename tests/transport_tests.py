"""Regression tests for transport startup cleanup and repeated close."""
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from genseki.uhp import UhpProcess


class TransportTests(unittest.TestCase):
    def test_startup_line_flood_is_reaped(self):
        original = subprocess.Popen
        children = []
        def capture(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child
        with patch('genseki.uhp.subprocess.Popen', side_effect=capture):
            with self.assertRaises(RuntimeError):
                UhpProcess([sys.executable, '-u', '-c',
                            'import sys,time;sys.stdout.write("x"*100000);'
                            'sys.stdout.flush();time.sleep(30)'], max_line_bytes=128)
        self.assertIsNotNone(children[0].poll())
        self.assertTrue(children[0].stdout.closed)

    def test_response_limit_cleans_owned_child(self):
        engine = UhpProcess([sys.executable, '-u', '-c',
            'import sys,time;print("ok",flush=True);sys.stdin.readline();'
            'print("x"*80,flush=True);print("x"*80,flush=True);time.sleep(30)'],
            max_response_bytes=100)
        with self.assertRaisesRegex(RuntimeError, 'response byte limit'):
            engine.command('info')
        self.assertIsNotNone(engine.process.poll())
        self.assertFalse(engine.reader.is_alive())
        engine.close()

    def test_queue_flood_without_consumer_is_reaped(self):
        engine = UhpProcess([sys.executable, '-u', '-c',
            'import sys,time;print("ok",flush=True);sys.stdin.readline();'
            'sys.stdout.write("x\\n"*10000);sys.stdout.flush();time.sleep(30)'],
            max_queue_lines=4)
        engine.process.stdin.write(b'info\n')
        engine.process.stdin.flush()
        self.assertTrue(engine.finished.wait(5))
        with self.assertRaises(RuntimeError):
            engine.read_response(1)
        self.assertIsNotNone(engine.process.poll())
        self.assertFalse(engine.reader.is_alive())

    def test_utf8_wire_bytes_are_bounded(self):
        with self.assertRaises(RuntimeError):
            UhpProcess([sys.executable, '-u', '-c',
                'import sys;sys.stdout.buffer.write(bytes([195,169])*100+b"\\nok\\n");'
                'sys.stdout.flush()'], max_line_bytes=128)

    def test_queued_bytes_and_crlf_response_are_bounded(self):
        engine = UhpProcess([sys.executable, '-u', '-c',
            'import sys,time;print("ok",flush=True);sys.stdin.readline();'
            'sys.stdout.buffer.write(b"x"*60+b"\\r\\n"+b"y"*60+b"\\r\\n");'
            'sys.stdout.flush();time.sleep(30)'], max_queue_bytes=100)
        engine.process.stdin.write(b'info\n')
        engine.process.stdin.flush()
        self.assertTrue(engine.finished.wait(5))
        with self.assertRaises(RuntimeError):
            engine.read_response(1)
        self.assertLessEqual(engine.queued_bytes, 100)

    def test_invalid_utf8_is_rejected(self):
        with self.assertRaises(RuntimeError):
            UhpProcess([sys.executable, '-u', '-c',
                'import sys;sys.stdout.buffer.write(b"\\xff\\nok\\n");sys.stdout.flush()'])

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
                             'print("ok", flush=True)\nfor line in __import__("sys").stdin:\n'
                             ' if line.strip()=="exit": break\n print("ok", flush=True)'])
        self.assertEqual(engine.command('info')[0], ['ok'])
        engine.close()
        engine.close()
        self.assertIsNotNone(engine.process.poll())


if __name__ == '__main__':
    unittest.main()
