"""Python/native byte-lock interoperability on isolated paths under team scheduling."""
from pathlib import Path
import subprocess
import sys
import tempfile
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

if __name__=='__main__':unittest.main()
