"""Re-encoding preserves supervision and refuses missing child geometry."""
import copy
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import symmetry_retrain as migration

class ReencodeTests(unittest.TestCase):
    def test_preserves_metadata_and_encodes_all_children(self):
        row=dict(position='parent',features=[[99],[99]],feature_schema=4,source='teacher',
                 seed=7,game=3,opening_family='heldout',termination='ply_cap',outcome=None,
                 teacher_search_cp=-42,preferred_position='good',preferred_features=[[99],[99]],
                 alternative_position='other',alternative_features=[[99],[99]],
                 alternatives=[dict(position='good',cp=12,features=[[99],[99]])])
        original=copy.deepcopy(row)
        class Engine:position=None
        engine=Engine()
        def response(engine,command):
            if command.startswith('nu-loadposition '):engine.position=command.split(' ',1)[1];return []
            value={'parent':1,'good':2,'other':3}[engine.position]
            return [f'0: {value}',f'1: {value+10}','score 0']
        with patch.object(migration,'response',response):encoded=migration.encode(row,engine)
        self.assertEqual(row,original)
        self.assertEqual(encoded['features'],[[1],[11]])
        self.assertEqual(encoded['preferred_features'],[[2],[12]])
        self.assertEqual(encoded['alternative_features'],[[3],[13]])
        self.assertEqual(encoded['alternatives'][0]['features'],[[2],[12]])
        self.assertEqual(encoded['feature_schema'],6)
        for key in ('source','seed','game','opening_family','termination','outcome','teacher_search_cp'):
            self.assertEqual(encoded[key],original[key])

    def test_missing_child_coordinates_are_not_silently_discarded(self):
        row=dict(position='parent',features=[[1],[2]],preferred_features=[[3],[4]])
        with patch.object(migration,'response',return_value=['0: 1','1: 2','score 0']):
            with self.assertRaisesRegex(RuntimeError,'missing child coordinates'):
                migration.encode(row,object())

if __name__=='__main__':unittest.main()
