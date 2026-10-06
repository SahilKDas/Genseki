"""Lab redesign contracts; no training or arena jobs."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Alpha/tools'))
import gen2_lab as lab


class LabTests(unittest.TestCase):
    def test_white_and_black_regret_orientation(self):
        children=[dict(cp=100,prediction_white=-2),dict(cp=-20,prediction_white=3)]
        self.assertEqual(lab.choose_and_regret(children,1,'prediction_white'),(1,120))
        self.assertEqual(lab.choose_and_regret(children,-1,'prediction_white'),(0,120))

    def test_ties_and_nonfinite(self):
        self.assertEqual(lab.choose_and_regret([dict(cp=5,prediction_white=1),dict(cp=5,prediction_white=2)],1,'prediction_white')[1],0)
        with self.assertRaises(ValueError):lab.choose_and_regret([dict(cp=float('nan'),prediction_white=1)],1,'prediction_white')
        with self.assertRaises(ValueError):lab.choose_and_regret([],1,'prediction_white')

    def test_training_decisions_use_rules_and_native_clip(self):
        rows=[dict(alternatives=[dict(terminal=1),dict(terminal=None),dict(terminal=None,repetition_draw=True)])]
        self.assertEqual(lab.g.rule_aware_predictions(rows,[[-99,99,99]]),[[10.,5000/600,0.]])
        with self.assertRaises(ValueError):lab.g.rule_aware_predictions(rows,[[0]])

    def test_artifact_switch_is_rejected(self):
        original=lab.artifacts
        try:
            lab.artifacts=lambda _:dict(binary='new')
            with self.assertRaisesRegex(RuntimeError,'artifacts changed'):lab.verify_artifacts(None,dict(binary='old'))
        finally:lab.artifacts=original

    def test_opening_pairs_are_grouped(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'Alpha/tests') as folder:
            path=Path(folder)/'arena.json'
            moves=['wA1','bA1 wA1-','wQ -wA1','bQ bA1-','wS1 /wA1','bS1 bA1/']
            path.write_text(json.dumps(dict(config=dict(stage='development'),valid=True,games=[dict(index=i,opening_seed=123,moves=moves,termination='timeout',score=0) for i in range(2)])))
            rows=list(lab.legal_positions([path],8))
            self.assertEqual(len(rows),2)
            self.assertEqual(rows[0]['opening_family'],rows[1]['opening_family'])
            self.assertNotEqual(rows[0]['id'],rows[1]['id'])
            path.write_text(json.dumps(dict(config=dict(stage='development'),valid=False,games=[])))
            with self.assertRaises(RuntimeError):list(lab.legal_positions([path],8))

    def test_slice_flags_are_explicit_not_outcome_labels(self):
        position='G1|w|8|4|4|0,0=wQ,bB1;1,0=wA1;0,1=bA1;-1,1=bQ;-1,0=wS1'
        self.assertEqual(lab.slices(position,['Place(123, Ant)'],True),['queen_pressure','reserve_deployment','stacks','student_loss_line'])

    def test_search_parsing_records_completed_depth(self):
        original=lab.g.cmd
        try:
            lab.g.cmd=lambda *_: (['score -7 static -8 move pass','Principal variation: pass','Explored 23 nodes to depth 2. MBF=2.0'],.05)
            result=lab.search(None,4,250)
            self.assertEqual(result['depth'],2)
            self.assertEqual(result['score'],-7)
            self.assertEqual(result['milliseconds'],50)
        finally:lab.g.cmd=original

    def test_committed_smoke_decisions_are_full_width(self):
        files=list((lab.g.WORK/'lab-v1').glob('game-*.jsonl'))
        if not files:self.skipTest('collector smoke corpus not available')
        for path in files:
            row=json.loads(path.read_text());children=row['alternatives']
            self.assertTrue(row['full_width'])
            self.assertEqual(row['legal_count'],len(children))
            self.assertEqual(len(children),len({c['move'] for c in children}))
            if row['source_termination']!='natural':self.assertIsNone(row['outcome'])
            scores=[c['cp']*row['mover'] for c in children]
            self.assertEqual(scores,sorted(scores,reverse=True))
            for child in children:self.assertEqual(len(child['features']),2)


if __name__=='__main__':unittest.main()
