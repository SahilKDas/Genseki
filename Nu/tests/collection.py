"""Canonical counting must match the frozen SQL index without cumulative copies."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Nu/tools'));sys.path.insert(0,str(ROOT))
from collect_schema7 import accepted
from learning import index_corpus
from position_keys import position_key


class CollectionTests(unittest.TestCase):
    def test_count_matches_immutable_index(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'Nu/work') as folder:
            directory=Path(folder);paths=[];rows=[]
            for game in range(12):
                position=f'G1|w|8|4|4|0,0=wQ;{game+1},0=bQ'
                row=dict(source='unit',game=game,seed=1,ply=8,feature_schema=7,
                         opening_position=position,position=position,features=[[1],[2]],
                         strategic_prior_version=1,prior_white=0,outcome=None,termination='ply_cap')
                rows.append(row);paths.append(directory/f'game-{game:06d}.jsonl')
            split=lambda row:int(hashlib.sha256(position_key(row['opening_position']).encode()).hexdigest()[:8],16)%5==0
            other=next(row for row in rows if split(row)!=split(rows[0]))
            rows[0]['observed_children']=[dict(position=other['position'])]
            for path,row in zip(paths,rows):path.write_text(json.dumps(row)+'\n')
            db=index_corpus(paths,directory/'final.sqlite')
            expected=[db.execute('select count(*) from samples where split=?',(i,)).fetchone()[0] for i in (0,1)]
            db.close()
            self.assertEqual(accepted(directory,12),(sum(expected),expected))
            self.assertFalse(list(directory.glob('accepted-*.sqlite')))

    def test_reservation_excludes_both_openings_and_tactics(self):
        root=ROOT/'Nu/work/schema7-campaign/openings'
        if not root.exists():self.skipTest('no campaign reservation present')
        exclusion=json.loads((root/'exclusions.json').read_text())
        dev=json.loads((root/'development-openings.json').read_text())['openings']
        self.assertEqual(exclusion['qualification_count'],50)
        self.assertEqual(len(dev),10)
        self.assertTrue(all(position_key(r['position']) in exclusion['opening_families'] for r in dev))
        self.assertEqual(len(exclusion['opening_families']),60)


if __name__=='__main__':unittest.main()
