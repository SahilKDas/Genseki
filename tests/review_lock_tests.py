"""Python/native byte-lock interoperability on isolated paths under team scheduling."""
from pathlib import Path
import subprocess
import sys
import tempfile
import shutil
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from genseki.resources import job_lock
HELPER=Path(sys.argv.pop(1)).resolve()

class LockTests(unittest.TestCase):
    def setUp(self):
        folder=ROOT/'.tmp/team-genseki/developer-3/test-work'
        folder.mkdir(parents=True,exist_ok=True)
        self.temp=tempfile.TemporaryDirectory(dir=folder);self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'heavy.lock'

    def test_python_excludes_native_and_release(self):
        with job_lock(self.path):
            self.assertEqual(subprocess.run([str(HELPER),'probe',str(self.path)],timeout=5).returncode,75)
        self.assertEqual(subprocess.run([str(HELPER),'probe',str(self.path)],timeout=5).returncode,0)

    def test_native_excludes_python_and_crash_releases(self):
        child=subprocess.Popen([str(HELPER),'hold',str(self.path)],stdout=subprocess.PIPE,text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(),'owned')
            with self.assertRaises(OSError):
                with job_lock(self.path):pass
            self.assertEqual(subprocess.run([str(HELPER),'probe',str(self.path)],timeout=5).returncode,75)
        finally:
            child.kill();child.wait(timeout=5);child.stdout.close()
        with job_lock(self.path):pass

    def test_review_finds_executable_workspace_from_external_directory(self):
        # An isolated workspace avoids contending with actual research jobs.
        workspace=Path(self.temp.name)/'workspace'
        binary=workspace/'build'/HELPER.name
        binary.parent.mkdir(parents=True)
        shutil.copyfile(HELPER,binary)
        (workspace/'constraints_on_SahilKDas_device.md').write_text('test workspace\n')
        outside=Path(self.temp.name)/'outside'
        outside.mkdir()
        def claim():
            return subprocess.run([str(binary),'claim','unused'],cwd=outside,
                                  timeout=5).returncode
        self.assertEqual(claim(),0)
        for path in (workspace/'.tmp/team-genseki/heavy.lock',
                     workspace/'reports/work/heavy-job.lock'):
            with job_lock(path):
                self.assertEqual(claim(),75)
            self.assertEqual(claim(),0)

if __name__=='__main__':unittest.main()
