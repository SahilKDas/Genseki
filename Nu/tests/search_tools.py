import sys
from pathlib import Path
import unittest
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from export_search_evidence import public_copy
from incumbent import verified_settings
from promote_search import complete,scored
from arena import VALIDATION_POLICY,MEMORY_POLICY
from evidence import atomic_json


class SearchTools(unittest.TestCase):
    def test_atomic_json_hash_bytes_match_git_lf_policy(self):
        scratch=Path(__file__).resolve().parents[2]/'.tmp';scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=scratch) as directory:
            path=Path(directory)/'report.json';atomic_json(path,{'points':15.5})
            self.assertNotIn(b'\r\n',path.read_bytes())
    def test_redaction_is_path_platform_independent(self):
        self.assertEqual(public_copy({'invocation':[r'C:\Users\private\engine.exe','--model','/Users/private/model.nnue']}),
                         {'invocation':['engine.exe','--model','model.nnue']})
        for value in (r'C:\Users\private\x','/Users/private/x'):
            with self.assertRaises(RuntimeError):public_copy({'unexpected':value})
        self.assertEqual(public_copy([{'points':6,'games':20}]),[{'points':6,'games':20}])

    def test_registered_settings_are_bounded_and_typed(self):
        accepted={'Threads':8,'TableMiB':16,'ThreatPlies':1,'DeadlineGuard':True,'RootPVS':False,'RootPVFirst':True}
        self.assertEqual(verified_settings({'uhp_settings':accepted}),accepted)
        for bad in ({'Threads':13},{'Threads':True},{'ThreatPlies':5},{'RootPVS':'True'},{'unknown':True}):
            with self.assertRaises(RuntimeError):verified_settings({'uhp_settings':bad})

    def test_timeout_losses_and_color_orientation(self):
        self.assertEqual(scored({'termination':'timeout','timeout_side':'Nu'}),0)
        self.assertEqual(scored({'termination':'timeout','timeout_side':'Opponent'}),1)
        self.assertEqual(scored({'termination':'natural','result':'BlackWins','nu_color':'white'}),0)
        self.assertEqual(scored({'termination':'natural','result':'BlackWins','nu_color':'black'}),1)

    def test_promotion_evidence_must_be_complete_mirrored_and_scored(self):
        rows=[dict(pair=i//2,nu_color='white' if i%2==0 else 'black',score=.5,termination='ply_cap',result='Draw') for i in range(20)]
        report=dict(completed=True,rejected=False,expected_games=20,games=rows,points=10,
            milliseconds=250,internal_ms=230,threads=8,cap=160,depth_limit=64,table_mib=16,
            background_pondering=False,validation_policy=VALIDATION_POLICY,memory_policy=MEMORY_POLICY)
        complete(report)
        for field,value in [('points',13),('threads',12),('completed',False),('rejected',True)]:
            changed={**report,field:value}
            with self.assertRaises(RuntimeError):complete(changed)
        rows[0]['nu_color']='black'
        with self.assertRaises(RuntimeError):complete(report)


if __name__=='__main__':unittest.main()
