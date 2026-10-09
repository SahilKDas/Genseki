"""Benchmark recovery must reject changed pins before modifying evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Nu/tools'))
import benchmark_schema7 as benchmark
import cache_benchmark
from evidence import digest


class RecoveryTests(unittest.TestCase):
    def test_cache_evidence_is_not_overwritten(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'Nu/work') as temporary:
            directory=Path(temporary)
            report=directory/'baseline.json';report.write_text('retained',encoding='utf8')
            argv=['cache_benchmark','--engine',str(directory/'missing'),
                  '--benchmark',str(directory/'missing'),'--model',str(directory/'missing'),
                  '--output',str(directory),'--lane','baseline']
            with patch.object(sys,'argv',argv),patch.object(cache_benchmark,'resource_guard'),patch.object(cache_benchmark.subprocess,'run') as process:
                with self.assertRaisesRegex(RuntimeError,'overwrite'):
                    cache_benchmark.main()
                process.assert_not_called()
            self.assertEqual(report.read_text(),'retained')

    def check_rejected(self,change):
        with tempfile.TemporaryDirectory(dir=ROOT/'Nu/work') as temporary:
            directory=Path(temporary);artifact=directory/'artifact';artifact.write_bytes(b'pinned')
            output=directory/'report';output.mkdir()
            roots=output/'roots.txt';roots.write_text('retained evidence',encoding='utf8')
            saved=dict(version=2,models_sha256=[digest(artifact)])
            for key in ('engine_sha256','cost_engine_sha256','referee_sha256','openings_sha256','gen1_sha256'):
                saved[key]=digest(artifact)
            change(saved,artifact)
            report=output/'benchmark.json';report.write_text(json.dumps(saved),encoding='utf8')
            original=report.read_bytes()
            argv=['benchmark','--engine',str(artifact),'--cost-engine',str(artifact),
                  '--referee',str(artifact),'--models',str(artifact),'--openings',str(artifact),
                  '--gen1',str(artifact),'--output',str(output),'--resume']
            with patch.object(sys,'argv',argv),patch.object(benchmark,'UhpProcess') as process:
                with self.assertRaisesRegex(RuntimeError,'pin/version mismatch'):benchmark.main()
                process.assert_not_called()
            self.assertEqual(roots.read_text(encoding='utf8'),'retained evidence')
            self.assertEqual(report.read_bytes(),original)

    def test_old_policy_rejected_without_rewriting(self):
        self.check_rejected(lambda saved,artifact:saved.update(version=1))

    def test_changed_binary_rejected_without_rewriting(self):
        self.check_rejected(lambda saved,artifact:artifact.write_bytes(b'changed'))


if __name__=='__main__':unittest.main()
