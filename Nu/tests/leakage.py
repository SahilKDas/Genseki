"""Canonical parent/child exclusions and stale index contracts."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import learning
WORK=Path(__file__).resolve().parents[1]/'work'
WORK.mkdir(exist_ok=True)


class LeakageTests(unittest.TestCase):
    def families(self):
        return [next(f'f{i}' for i in range(100) if
            (int(hashlib.sha256(f'f{i}'.encode()).hexdigest()[:8],16)%5==0)==bool(split))
            for split in (0,1)]

    def row(self,schema,game,family,position):
        row=dict(source='unit',seed=1,game=game,ply=8,feature_schema=schema,
                 opening_family=family,position=position,features=[[1],[2]])
        if schema in (5,7):row.update(prior_white=0,strategic_prior_version=1)
        return row

    def test_equivalent_parents_never_cross_splits(self):
        for schema in (5,6,7):
            for second in ('G1|w|8|4|4|9,-3=wQ;10,-3=bQ;11,-3=wA2',
                           'G1|w|8|4|4|0,0=wQ;0,1=bQ;0,2=wA1'):
                with tempfile.TemporaryDirectory(dir=WORK) as folder:
                    root=Path(folder);data=root/'data.jsonl';families=self.families()
                    rows=[self.row(schema,0,families[0],'G1|w|8|4|4|0,0=wQ;1,0=bQ;2,0=wA1'),
                          self.row(schema,1,families[1],second)]
                    data.write_text('\n'.join(map(json.dumps,rows)))
                    db=learning.index_corpus([data],root/'index.sqlite')
                    self.assertEqual(db.execute('select count(*) from samples').fetchone()[0],0)
                    self.assertEqual(db.execute('select value from metadata where key="position_key_version"').fetchone()[0],
                                     'base-symmetry-opening-v2')
                    db.close()

    def test_child_exposure_removes_both_split_parents(self):
        for schema in (6,7):
            with tempfile.TemporaryDirectory(dir=WORK) as folder:
                root=Path(folder);data=root/'data.jsonl';families=self.families()
                a=self.row(schema,0,families[0],'G1|w|8|4|4|0,0=wQ;1,0=bQ;2,0=wA1')
                b=self.row(schema,1,families[1],'G1|w|8|4|4|0,0=wQ;1,0=bQ')
                a['alternatives']=[dict(position='G1|w|8|4|4|10,10=wQ;10,11=bQ',features=[[1],[2]],cp=0,prior_white=0)]
                data.write_text('\n'.join(map(json.dumps,[a,b])))
                db=learning.index_corpus([data],root/'index.sqlite')
                self.assertEqual(db.execute('select count(*) from samples').fetchone()[0],0)
                db.execute('update metadata set value="old" where key="identity"');db.commit();db.close()
                with self.assertRaisesRegex(RuntimeError,'identity mismatch'):
                    learning.index_corpus([data],root/'index.sqlite')


if __name__=='__main__':unittest.main()
