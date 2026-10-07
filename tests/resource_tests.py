"""Resource and lock regressions; no engines, training or matches."""
import ctypes
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'Alpha/tools'))
from genseki import resources, gauntlet
import gen2
import gen2_lab


class ResourceTests(unittest.TestCase):
    def test_ram_query_without_rho(self):
        self.assertGreater(resources.available_ram(), 0)
        self.assertIs(gen2.available_ram, resources.available_ram)
        self.assertIs(gauntlet.available_ram, resources.available_ram)
        with patch.object(gen2, 'available_ram', return_value=3*1024**3), \
                patch.object(gen2.shutil, 'disk_usage', return_value=SimpleNamespace(free=1024**3)):
            gen2.floors()
        with patch.object(gen2, 'available_ram', return_value=1024**3):
            with self.assertRaisesRegex(RuntimeError, 'RAM below'):
                gen2.floors()

    def test_ram_query_failure_is_closed(self):
        def fail(pointer):
            return 0
        fake = SimpleNamespace(kernel32=SimpleNamespace(GlobalMemoryStatusEx=fail))
        with patch.object(resources.os, 'name', 'nt'), \
                patch.object(ctypes, 'windll', fake, create=True):
            with self.assertRaises(OSError):
                resources.available_ram()

    def test_gauntlet_blocks_lab_and_ignores_itself(self):
        for mode in ('collect', 'audit', 'compare'):
            process = dict(ProcessId=gauntlet.os.getpid()+1, Name='python.exe',
                           CommandLine=f'python Alpha\\tools\\gen2_lab.py {mode}')
            with patch.object(gauntlet.os, 'name', 'nt'), \
                    patch.object(gauntlet, 'windows_processes', return_value=[process]):
                with self.assertRaisesRegex(RuntimeError, 'another training'):
                    gauntlet.preflight(False)
                process['ProcessId'] = gauntlet.os.getpid()
                gauntlet.preflight(False)

    def test_all_runners_share_the_same_lock_api(self):
        self.assertIs(gen2.job_lock, resources.job_lock)
        self.assertIs(gen2_lab.g.job_lock, resources.job_lock)
        self.assertIs(gauntlet.job_lock, resources.job_lock)
        self.assertEqual(gen2.heavy_job_path(ROOT), gauntlet.heavy_job_path(ROOT))

    def test_gen2_entrypoints_reject_held_shared_lock_before_work(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder:
            root = Path(folder)
            with patch.object(gen2, 'ROOT', root), patch.object(gen2, 'WORK', root/'work'):
                with resources.job_lock(resources.heavy_job_path(root)):
                    with patch.object(sys, 'argv', ['gen2.py', 'prepare']), \
                            patch.object(gen2, 'prepare') as work:
                        with self.assertRaises(OSError):
                            gen2.main()
                        work.assert_not_called()
                    with patch.object(sys, 'argv', ['gen2_lab.py', 'collect', '--model',
                            'model.nnue', '--sources', 'arena.json', '--stage-id', 'test']), \
                            patch.object(gen2_lab, 'sources_for', return_value=[]), \
                            patch.object(gen2_lab, 'collect') as work:
                        with self.assertRaises(OSError):
                            gen2_lab.main()
                        work.assert_not_called()

    def test_gauntlet_entrypoint_rejects_held_shared_lock_before_engines(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder:
            root = Path(folder)
            with resources.job_lock(resources.heavy_job_path(root)), \
                    patch.object(gauntlet, 'ROOT', root), \
                    patch.object(gauntlet, 'preflight') as preflight:
                result = gauntlet.main(['--engine-a', sys.executable, '--engine-b',
                    sys.executable, '--referee', sys.executable, '--no-gui',
                    '--output', str(root/'output')])
                self.assertEqual(result, 1)
                preflight.assert_not_called()

    def contender(self, path):
        code = ('import sys; from genseki.resources import job_lock\n'
                'try:\n'
                ' with job_lock(sys.argv[1]): pass\n'
                'except OSError: sys.exit(7)\n')
        return subprocess.run([sys.executable, '-B', '-c', code, str(path)],
                              cwd=ROOT, capture_output=True, text=True, timeout=10)

    def test_cross_process_exclusion_and_exception_release(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder:
            path = resources.heavy_job_path(folder)
            with self.assertRaisesRegex(ValueError, 'test interruption'):
                with resources.job_lock(path):
                    self.assertEqual(self.contender(path).returncode, 7)
                    raise ValueError('test interruption')
            result = self.contender(path)
            self.assertEqual(result.returncode, 0, result.stderr)
            # A leftover file is not a live lock.
            self.assertEqual(self.contender(path).returncode, 0)


if __name__ == '__main__':
    unittest.main()
