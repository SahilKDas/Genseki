"""Resumed matches must retain artifact identities and mirrored game order."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Nu/tools'))
import arena

class ResumeTests(unittest.TestCase):
    def fixture(self,root):
        artifact=root/'fixture';artifact.write_bytes(b'fixture')
        sha=hashlib.sha256(b'fixture').hexdigest()
        rows=[dict(pair=i//2,opening_seed=71000+i//2,nu_color='white' if i%2==0 else 'black',score=.5) for i in range(20)]
        report=dict(kind='development',games=rows,points=10,expected_games=20,completed=True,rejected=False,
            model_sha256=sha,engine_sha256=sha,opponent_sha256=sha,milliseconds=250,internal_ms=230,
            threads=1,cap=160,repetition_policy=arena.REPETITION_POLICY,threat_plies=0,lmr=False,seed_base=71000,
            hybrid=False,hybrid_weight=100,hybrid_terms=63,
            opponent_search_policy='equal-nu-search-v1',
            invocation=[str(artifact),'--model',str(artifact)],opponent_model_sha256=sha,
            opponent_version=None,opponent_revision=None,table_mib=16,background_pondering=False,random_opening=False,
            referee_sha256=sha,validation_policy=arena.VALIDATION_POLICY,memory_policy=arena.MEMORY_POLICY,depth_limit=64)
        path=root/'match.json';path.write_text(json.dumps(report))
        args=['arena','--engine',str(artifact),'--model',str(artifact),'--opponent',str(artifact),
              '--opponent-model',str(artifact),'--referee',str(artifact),'--output',str(path),'--resume']
        return args,path,report

    def test_completed_match_is_not_replayed(self):
        with tempfile.TemporaryDirectory() as folder:
            args,path,_=self.fixture(Path(folder));before=path.read_bytes()
            with patch.object(sys,'argv',args),patch.object(arena,'UhpProcess') as engine:
                arena.main();engine.assert_not_called()
            self.assertEqual(path.read_bytes(),before)

    def test_changed_identity_or_mirrored_order_rejected(self):
        for field in ('model_sha256','validation_policy','depth_limit','referee_sha256','hybrid','hybrid_weight','hybrid_terms','opponent_search_policy','order','rejected'):
            with tempfile.TemporaryDirectory() as folder:
                args,path,report=self.fixture(Path(folder))
                if field=='order':report['games'][0]['nu_color']='black'
                elif field=='rejected':report['rejected']=True
                else:report[field]='changed'
                path.write_text(json.dumps(report));before=path.read_bytes()
                with patch.object(sys,'argv',args),patch.object(arena,'UhpProcess') as engine:
                    with self.assertRaises(RuntimeError):arena.main()
                    engine.assert_not_called()
                self.assertEqual(path.read_bytes(),before)

    def test_boards_and_not_notation_must_agree(self):
        def fake(peer,text):
            if 'bad' in text:raise RuntimeError('invalid replay')
            return (['different' if 'divergent' in text else 'same'],0)
        with patch.object(arena,'command',fake):
            self.assertEqual(arena.validate_boards(None,['Base;InProgress;White[3];notation-a','Base;InProgress;White[3];notation-b']), 'same')
            for state in ('Base;InProgress;White[3];divergent','Base;InProgress;White[3];bad','Base;InProgress;Black[3];notation'):
                with self.assertRaises(RuntimeError):arena.validate_boards(None,['Base;InProgress;White[3];a',state])

if __name__=='__main__':unittest.main()
