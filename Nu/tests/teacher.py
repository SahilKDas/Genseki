"""Frozen-teacher targets must not turn printed mate values into regression labels."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Nu/tools'));sys.path.insert(0,str(ROOT))
from gen1_teacher import parse_diagnostics
from collect_schema7 import white_target,legal_notation


class TeacherTests(unittest.TestCase):
    def test_completed_and_mate_targets(self):
        for printed,expected in (('42',42),('-17',-17),('\u221e',None),('-\u221e',None)):
            result=parse_diagnostics(f'Iterative fullsearch depth 5 took 123ms; value {printed}; bestmove=move\nExplored 100 nodes to depth 5.')
            self.assertEqual(result['raw_score'],expected)
            target=dict(result,orientation='side_to_move')
            self.assertEqual(white_target(target,-1),None if expected is None else -4*expected)
        with self.assertRaises(RuntimeError):parse_diagnostics('no completed search')
        with self.assertRaises(RuntimeError):parse_diagnostics('fullsearch depth 4 took 1ms; value 1;\nExplored 5 nodes to depth 5.')

    def test_equivalent_move_notation(self):
        def response(peer,text):return ['same' if text.endswith(('preferred','equivalent')) else 'other']
        with patch('collect_schema7.response',response):
            self.assertEqual(legal_notation(None,'preferred',['different','equivalent']),'equivalent')
            with self.assertRaises(RuntimeError):legal_notation(None,'preferred',['different'])


if __name__=='__main__':unittest.main()
