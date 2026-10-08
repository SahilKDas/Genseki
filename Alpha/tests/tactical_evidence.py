"""Fixture labels and leakage tests; no training/search jobs."""
import copy
from pathlib import Path
import sys
import time
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Alpha/tools'))
import tactical_evidence as t

class EvidenceTests(unittest.TestCase):
    def test_key_preserves_side_stacks_and_queen_phase(self):
        position='G1|w|8|4|4|0,0=wQ,bB1;1,0=bQ;0,1=wA1'
        self.assertNotEqual(t.position_key(position),t.position_key(position.replace('|w|','|b|')))
        self.assertNotEqual(t.position_key(position),t.position_key(position.replace('wQ,bB1','bB1,wQ')))
        self.assertEqual(t.position_key(position),t.position_key(position.replace('wA1','wA2')))

    def test_key_removes_translation_rotation_and_reflection(self):
        a='G1|w|8|4|4|0,0=wQ;1,0=bQ;0,1=wA1'
        b='G1|w|12|6|6|4,4=wQ;4,5=bQ;3,5=wA1'
        c='G1|w|8|4|4|0,0=wQ;0,1=bQ;1,0=wA1'
        self.assertEqual(t.position_key(a),t.position_key(b))
        self.assertEqual(t.position_key(a),t.position_key(c))

    def test_source_game_and_opening_are_never_split(self):
        rows=[dict(id=str(i),source_game='same',opening_family='opening-'+str(i),position_key=str(i),exposures=[str(i)]) for i in range(8)]
        kept,_=t.split_records(rows)
        self.assertEqual(len({r['split'] for r in kept}),1)
        self.assertEqual(len({r['opening_family'] for r in kept}),1)

    def test_cross_split_child_exposure_removes_both(self):
        families={}
        for i in range(100):
            row=dict(id=str(i),source_game=str(i),opening_family='opening-'+str(i),position_key=str(i),exposures=['shared'])
            classified,_=t.split_records([copy.deepcopy(row)])
            families.setdefault(classified[0]['split'],row)
        kept,excluded=t.split_records(list(families.values()))
        self.assertEqual(kept,[]);self.assertEqual(len(excluded),2)

    def test_interrupted_proof_never_supplies_safe_moves(self):
        class Fake:
            def command(self,text,timeout):raise TimeoutError
        result=t.prove(Fake(),'Base',1,time.monotonic()+10)
        self.assertEqual(result['proof']['status'],'unknown')
        self.assertEqual(result['proof']['safe_moves'],[])
        self.assertFalse(result['proof']['all_roots_checked'])

    def test_covered_queen_and_simultaneous_surround(self):
        ring=[(1,0),(0,1),(-1,1),(-1,0),(0,-1),(1,-1)]
        cells=['0,0=wQ,bB1']+[f'{q},{r}=bA1' for q,r in ring]
        position='G1|b|10|5|5|'+';'.join(cells)
        self.assertEqual(t.surround_result(position),'BlackWins')
        cells+=['4,0=bQ']+[f'{q+4},{r}=wA1' for q,r in ring]
        self.assertEqual(t.surround_result('G1|b|10|5|5|'+';'.join(cells)),'Draw')

    def test_immediate_win_checked_before_defensive_reply_work(self):
        ring=[(1,0),(0,1),(-1,1),(-1,0),(0,-1),(1,-1)]
        winner='G1|b|10|5|5|'+';'.join(['0,0=bQ','4,0=wQ']+[f'{q},{r}=wA1' for q,r in ring])
        root='G1|w|8|4|4|0,0=bQ;4,0=wQ'
        class Fake:
            calls=[]
            def command(self,text,timeout):
                self.calls.append(text)
                if text=='newgame Base':return ['Base;InProgress;White[5]','ok'],0
                if text=='genseki-position':return [root,'ok'],0
                if text=='validmoves':return ['bad;win','ok'],0
                if text=='genseki-children':return ['bad\t'+root,'win\t'+winner,'ok'],0
                if text=='play win':return ['Base;WhiteWins;Black[5]','ok'],0
                if text=='undo':return ['Base;InProgress;White[5]','ok'],0
                raise AssertionError(text)
        fake=Fake();result=t.prove(fake,'Base',1000,time.monotonic()+10)
        self.assertEqual(result['proof']['winning_moves'],['win'])
        self.assertEqual(result['proof']['kind'],'immediate_win')
        self.assertNotIn('play bad',fake.calls)

if __name__=='__main__':unittest.main()
