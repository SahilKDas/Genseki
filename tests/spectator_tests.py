"""Validate native snapshot parsing without starting engines or opening windows."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
BINARY = Path(sys.argv.pop(1)).resolve()
FRAME = ['GENSEKI_SPECTATOR_V1', 'Gauntlet', 'Game 1/2', 'A', 'B', 'A 0 : B 0',
         'Base;InProgress;White[3];wA1;bA1 wA1-;wQ -wA1;bQ bA1-']


class SpectatorTests(unittest.TestCase):
    def check_frame(self, payload, expected):
        with tempfile.TemporaryDirectory(dir=ROOT/'Lab') as folder:
            path = Path(folder)/'live.txt'
            path.write_bytes(payload)
            result = subprocess.run([str(BINARY), '--check-spectator', str(path)], timeout=10)
            self.assertEqual(result.returncode, expected)

    def test_lf_and_crlf(self):
        for separator in ('\n', '\r\n'):
            with self.subTest(separator=repr(separator)):
                self.check_frame((separator.join(FRAME)+separator).encode(), 0)

    def test_partial_or_wrong_schema_is_rejected(self):
        self.check_frame('\n'.join(FRAME[:4]).encode(), 1)
        self.check_frame(('wrong\n'+'\n'.join(FRAME[1:])+'\n').encode(), 1)

    def test_bad_game_is_rejected(self):
        self.check_frame(('\n'.join(FRAME[:6])+ '\ninvalid game\n').encode(), 1)


if __name__ == '__main__':
    unittest.main()
