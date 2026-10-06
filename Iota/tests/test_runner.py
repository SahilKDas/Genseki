import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import match
from common import UhpProcess,command,ROOT
from models import Network,parse_encoding
import torch
import tempfile
import common
import json
from types import SimpleNamespace

class RunnerTests(unittest.TestCase):
    def test_reference_aliases_compare_replayed_state(self):
        rules=UhpProcess([str(ROOT/'build/iota.exe')]);checker=UhpProcess([str(ROOT/'build/iota.exe')])
        expected='Base;InProgress;Black[4];wG1;bB1 -wG1;wQ wG1/;bS1 \\bB1;wA1 \\wQ;bQ /bB1;wA2 wG1-'
        actual=expected.rsplit(';',1)[0]+';wA2 wQ\\'
        try:
            command(rules,'newgame '+expected)
            match.verify_state(checker,rules,actual,expected)
            with self.assertRaises(RuntimeError):match.verify_state(checker,rules,actual.replace('Black[4]','White[4]'),expected)
        finally:rules.close();checker.close()

    @unittest.skipUnless(common.os.name=='nt','Windows process preflight')
    def test_other_heavy_jobs_block_iota(self):
        for text in ('python Nu\\tools\\arena.py --games 10','python Alpha/tools/gen2.py arena --games 20'):
            result=SimpleNamespace(stdout=json.dumps([dict(ProcessId=common.os.getpid()+100,CommandLine=text)]))
            with patch.object(common,'guard'),patch.object(common.subprocess,'run',return_value=result):
                with self.assertRaisesRegex(RuntimeError,'another heavy'):common.acquire_job()

    def test_invalid_encoding_indices(self):
        row=' '.join(map(str,[0,0]+[0]*80+[99]*6))
        action='action '+' '.join(map(str,[-1,0]+[0]*16))
        with self.assertRaises(ValueError):parse_encoding(['1 80',row,action])

    def test_options_and_repetition_identity(self):
        engine=UhpProcess([str(ROOT/'build/iota.exe')])
        try:
            options,_=command(engine,'options')
            for option in options:
                queried,_=command(engine,'options get '+option.split(';')[0])
                self.assertEqual(queried,[option])
            command(engine,'newgame Base')
            identity,_=command(engine,'iota-repetition')
            self.assertEqual(identity,['0:0:'])
        finally:engine.close()

    def test_numthreads_is_pinned_and_verified(self):
        calls=[]
        def command(engine,text):
            calls.append(text)
            if text=='options':
                value='1' if 'options set NumThreads 1' in calls else '12'
                return [f'NumThreads;int;{value};12;1;12','BackgroundPondering;bool;False;False'],0
            return [],0
        with patch.object(match,'command',command):
            self.assertIn('NumThreads;int;1;12;1;12',match.pin_alpha(None))
        self.assertIn('options set BackgroundPondering False',calls)

    def test_ineffective_or_unknown_threads_rejected(self):
        for options in ([],['NumThreads;int;12;12;1;12']):
            with patch.object(match,'command',return_value=(options,0)):
                with self.assertRaises(RuntimeError):match.pin_alpha(None)

    def test_nonfinite_export_does_not_replace_artifact(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as directory:
            path=Path(directory)/'model.iota'
            model=Network();model.export(path);before=path.read_bytes()
            with torch.no_grad():model.input.weight[0,0]=float('nan')
            with self.assertRaises(ValueError):model.export(path)
            self.assertEqual(before,path.read_bytes())

if __name__=='__main__':unittest.main()
