"""Model rejection, option isolation, and frozen Gen 1 score regressions."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import sqlite3
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Alpha/tools'))
import gen2

class Gen2Tests(unittest.TestCase):
    def test_frozen_gen1_hash(self):
        self.assertEqual(gen2.digest(gen2.WORK/'gen1.exe'),gen2.read(gen2.REPORT/'gen1.json')['sha256'])

    def test_default_fixed_depth_scores(self):
        games=['Base','Base;;;wA1;bA1 wA1-;wQ -wA1;bQ bA1-']
        for game in games:
            scores=[]
            for binary in (gen2.WORK/'gen1.exe',gen2.ENGINE):
                result=subprocess.run([str(binary),'profile-search',game,'3','1','1'],capture_output=True,text=True,timeout=30,check=True)
                scores.append([x for x in result.stdout.splitlines() if x.startswith('root_value ')])
            self.assertEqual(scores[0],scores[1]);self.assertTrue(scores[0])

    def test_invalid_models_fail_without_fallback(self):
        model=gen2.WORK/'nu-baseline.nnue';data=model.read_bytes()
        with tempfile.TemporaryDirectory(dir=gen2.WORK) as root:
            path=Path(root)/'bad.nnue'
            for name,bytes_,trained in [('corrupt',data[:-1]+bytes([data[-1]^1]),True),('truncated',data[:30],True),('untrained',data,False),('schema',data[:8]+(99).to_bytes(4,'little')+data[12:],True),('old-schema',data[:8]+(1).to_bytes(4,'little')+data[12:],True)]:
                with self.subTest(name=name):
                    path.write_bytes(bytes_);gen2.atomic(str(path)+'.alpha.json',dict(trained=trained,sha256=hashlib.sha256(bytes_).hexdigest(),score_scale=.25))
                    result=subprocess.run([str(gen2.ENGINE),'--evaluator','neural','--model',str(path)],input='',capture_output=True,text=True,timeout=10)
                    self.assertNotEqual(result.returncode,0)

    def test_model_switch_expansion_and_memory_rejection(self):
        with gen2.engine(gen2.ENGINE) as e:
            gen2.settings(e,2);gen2.cmd(e,'newgame Base')
            gen2.neural(e,gen2.WORK/'nu-baseline.nnue')
            for text in ('newgame Base+MLP','options set TableSizeMiB 1','options set ModelPath absent.nnue'):
                lines,_=e.command(text);self.assertTrue(any(x.startswith('err ') for x in lines))
                self.assertIn('neural',gen2.cmd(e,'options get Evaluator')[0][0])
            gen2.cmd(e,'options set BackgroundPondering True')
            gen2.cmd(e,'bestmove seconds 0.01')
            gen2.cmd(e,'options set Evaluator gen1')
            self.assertEqual(gen2.cmd(e,'alpha-eval')[0],['score 0'])
            score=gen2.cmd(e,'alpha-search 2 230')[0][0].split()[1]
            with gen2.engine(gen2.ENGINE) as fresh:
                gen2.settings(fresh,2);gen2.cmd(fresh,'newgame Base')
                self.assertEqual(score,gen2.cmd(fresh,'alpha-search 2 230')[0][0].split()[1])
            gen2.cmd(e,'newgame Base+MLP')

    def test_tactical_fixture_exclusion(self):
        sys.path.insert(0,str(ROOT/'Nu/tools'))
        from learning import position_key
        db=sqlite3.connect(gen2.WORK/'training-index.sqlite')
        try:
            fixtures=[f'G1|w|{turns*2}|{turns}|{turns}|0,-1=bQ;0,0=wQ,bB1' for turns in (2,3,4)]
            fixtures.extend(f'G1|b|7|4|{turns}|-1,0=wA1;-1,1=bA2;0,-1=bQ;0,0=wQ;0,1=wS2;1,-1=wS1;1,0=bA1' for turns in (3,4))
            for position in fixtures:
                self.assertEqual(db.execute('select count(*) from samples where position=?',(position_key(position),)).fetchone()[0],0)
            with gen2.engine(ROOT/'build/genseki_rules.exe') as e:
                for fixture in gen2.read(ROOT/'Alpha/reports/profile-suite.json')['records']:
                    game=fixture['position']
                    if game.split(';')[0]!='Base':continue
                    gen2.cmd(e,'newgame Base')
                    for move in game.split(';')[3:]:
                        if move:gen2.cmd(e,'play '+move)
                    position=gen2.cmd(e,'genseki-position')[0][0]
                    self.assertEqual(db.execute('select count(*) from samples where position=?',(position_key(position),)).fetchone()[0],0)
        finally:db.close()

    def test_failed_screen_blocks_larger_development(self):
        args=SimpleNamespace(model=None,opponent=None,name='blocked-test',seconds=1,games=100,threads=1)
        with self.assertRaisesRegex(RuntimeError,'both passing 20-game screens'):gen2.arena(args)

    def test_stage_resume_does_not_extend_deadline(self):
        with tempfile.TemporaryDirectory(dir=gen2.WORK) as directory:
            path=Path(directory)/'stage.json'
            first,_=gen2.stage_start(path,{'binary':'pinned'},2,100)
            resumed,remaining=gen2.stage_start(path,{'binary':'pinned'},200,101)
            self.assertEqual(first['deadline'],resumed['deadline']);self.assertEqual(remaining,1)
            with self.assertRaisesRegex(RuntimeError,'deadline expired'):gen2.stage_start(path,{'binary':'pinned'},200,102)
            with self.assertRaisesRegex(RuntimeError,'resume mismatch'):gen2.stage_start(path,{'binary':'changed'},200,101)

    def test_completed_arena_openings_are_mirrored(self):
        with gen2.engine(ROOT/'build/genseki_rules.exe') as e:
            for file in gen2.REPORT.glob('*-vs-*.json'):
                report=gen2.read(file)
                if not report.get('complete'):continue
                for index in range(0,len(report['games']),2):
                    positions=[]
                    for game in report['games'][index:index+2]:
                        gen2.cmd(e,'newgame Base')
                        for move in game['moves'][:4]:gen2.cmd(e,'play '+move)
                        positions.append(gen2.cmd(e,'genseki-position')[0][0])
                    self.assertEqual(positions[0],positions[1])

if __name__=='__main__':unittest.main()
