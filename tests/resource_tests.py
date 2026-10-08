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

    def test_gauntlet_rejects_team_lock_before_work(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder:
            root = Path(folder)
            with resources.job_lock(resources.team_job_path(root)), \
                    patch.object(gauntlet, 'ROOT', root), \
                    patch.object(gauntlet, 'preflight') as preflight:
                result = gauntlet.main(['--engine-a', sys.executable, '--engine-b',
                    sys.executable, '--referee', sys.executable, '--no-gui',
                    '--output', str(root/'output')])
                self.assertEqual(result, 1)
                preflight.assert_not_called()
            with resources.job_lock(resources.team_job_path(root)):
                pass

    def test_trainer_snapshot_includes_required_helper(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder:
            root = Path(folder)
            tools = root/'Nu/tools'
            tools.mkdir(parents=True)
            for name in ('learning.py', 'train.py', 'evidence.py', 'decisions.py'):
                (tools/name).write_text('# fixture\n')
            (tools/'research_job.py').write_text('def check_deadline(): pass\n')
            with patch.object(gen2, 'ROOT', root), patch.object(gen2, 'WORK', root/'work'), \
                    patch.object(gen2, 'REPORT', root/'reports'):
                runtime = gen2.training_runtime()
                helper = runtime/'research_job.py'
                self.assertEqual(helper.read_bytes(), (tools/'research_job.py').read_bytes())
                helper.unlink()
                self.assertEqual(gen2.training_runtime(), runtime)
                helper.write_text('# tampered\n')
                with self.assertRaisesRegex(RuntimeError, 'pinned trainer changed'):
                    gen2.training_runtime()
                helper.write_bytes((tools/'research_job.py').read_bytes())
                pin = root/'reports/trainer-latest-pin.json'
                original = pin.read_bytes()
                (tools/'research_job.py').write_text('# changed source\n')
                with self.assertRaisesRegex(RuntimeError, 'latest Nu changed'):
                    gen2.training_runtime()
                self.assertEqual(pin.read_bytes(), original)

    def test_snapshot_helper_import_without_live_nu_path(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder:
            root = Path(folder)
            tools = root/'Nu/tools'
            tools.mkdir(parents=True)
            for name in ('learning.py', 'train.py', 'evidence.py', 'decisions.py', 'research_job.py'):
                (tools/name).write_bytes((ROOT/'Nu/tools'/name).read_bytes())
            with patch.object(gen2, 'ROOT', root), patch.object(gen2, 'WORK', root/'work'), \
                    patch.object(gen2, 'REPORT', root/'reports'):
                runtime = gen2.training_runtime()
                code = ('import sys; sys.path.insert(0,sys.argv[1]); '
                        'sys.path.insert(0,sys.argv[2]); '
                        'import research_job; research_job.check_deadline(); '
                        'assert research_job.__file__.startswith(sys.argv[2])')
                result = subprocess.run([sys.executable, '-B', '-c', code, str(ROOT),
                    str(runtime)], cwd=root, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)

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

    def test_process_death_releases_lock(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as folder:
            path = resources.heavy_job_path(folder)
            code = ('import sys,time; from genseki.resources import job_lock\n'
                    'with job_lock(sys.argv[1]):\n'
                    ' print("locked",flush=True)\n'
                    ' time.sleep(30)\n')
            child = subprocess.Popen([sys.executable, '-B', '-u', '-c', code, str(path)],
                cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                self.assertEqual(child.stdout.readline().strip(), 'locked')
                self.assertEqual(self.contender(path).returncode, 7)
                child.kill()
                child.wait(timeout=5)
                self.assertEqual(self.contender(path).returncode, 0)
            finally:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)


if __name__ == '__main__':
    unittest.main()
