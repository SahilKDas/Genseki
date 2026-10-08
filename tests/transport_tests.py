"""Regression tests for transport startup cleanup and repeated close."""
import subprocess
import time
import threading
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
        engine.close()
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
        engine.close()
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
        engine.close()
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

    def test_blocked_write_uses_request_deadline(self):
        for _ in range(3):
            engine = UhpProcess([sys.executable, '-u', '-c',
                'import time;print("ok",flush=True);time.sleep(30)'])
            try:
                started = time.perf_counter()
                with self.assertRaises(TimeoutError):engine.command('x'*500000, .01)
                self.assertLess(time.perf_counter()-started, .1)
                with self.assertRaises(RuntimeError):engine.command('info')
            finally:engine.close()
            self.assertFalse(engine.writer.is_alive())
            self.assertFalse(engine.reader.is_alive())

    def test_response_timeout_invalidates_session(self):
        engine = UhpProcess([sys.executable, '-u', '-c',
            'import sys,time;print("ok",flush=True);sys.stdin.readline();time.sleep(30)'])
        try:
            started = time.perf_counter()
            with self.assertRaises(TimeoutError):engine.command('info', .01)
            self.assertLess(time.perf_counter()-started, .1)
            with self.assertRaises(RuntimeError):engine.command('info')
        finally:engine.close()

    def test_concurrent_commands_are_serialized(self):
        engine=UhpProcess([sys.executable,'-u','-c',
            'import sys;print("ok",flush=True)\nfor line in sys.stdin:\n print(line.strip(),flush=True);print("ok",flush=True)'])
        results={}
        threads=[threading.Thread(target=lambda value=value:results.update({value:engine.command(value)[0]}))
                 for value in ('one','two')]
        try:
            for thread in threads:thread.start()
            for thread in threads:thread.join(1)
            self.assertEqual(results,{'one':['one','ok'],'two':['two','ok']})
        finally:engine.close()

    def test_command_lock_is_deadline_bounded(self):
        engine=UhpProcess([sys.executable,'-u','-c',
            'import time;print("ok",flush=True);time.sleep(30)'])
        engine.command_guard.acquire()
        try:
            started=time.perf_counter()
            with self.assertRaises(TimeoutError):engine.command('info',.01)
            self.assertLess(time.perf_counter()-started,.1)
        finally:
            engine.command_guard.release();engine.close()

    def test_writer_completes_partial_writes(self):
        import queue
        from types import SimpleNamespace
        chunks=[]
        class Stream:
            def write(self,payload):
                count=min(2,len(payload));chunks.append(payload[:count]);return count
            def flush(self):chunks.append(b'flush')
        engine=object.__new__(UhpProcess)
        engine.closed=False;engine.failure=None;engine.writes=queue.Queue(maxsize=2)
        engine.process=SimpleNamespace(stdin=Stream())
        done=threading.Event();errors=[]
        engine.writes.put((b'abcdef',done,errors));engine.writes.put(None)
        engine._write_lines()
        self.assertTrue(done.is_set());self.assertEqual(errors,[])
        self.assertEqual(chunks,[b'ab',b'cd',b'ef',b'flush'])


if __name__ == '__main__':
    unittest.main()
