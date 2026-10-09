"""Self-contained provenance and canonical-exclusion regressions."""
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Alpha/tools'))
sys.path.insert(0,str(ROOT/'Nu/tools'))
import gen2
from position_keys import position_key

class AuditRepairs(unittest.TestCase):
    def test_trainer_pins_canonical_helper(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as directory:
            root=Path(directory)
            source=root/'Nu/tools';source.mkdir(parents=True)
            for name in ('learning','train','evidence','decisions','research_job','position_keys'):
                (source/(name+'.py')).write_text('value=1\n')
            with patch.multiple(gen2,ROOT=root,WORK=root/'work',REPORT=root/'report'):
                frozen=gen2.training_runtime()
                self.assertEqual((frozen/'position_keys.py').read_bytes(),(source/'position_keys.py').read_bytes())
                (source/'position_keys.py').write_text('value=2\n')
                with self.assertRaisesRegex(RuntimeError,'changed after pinning'):gen2.training_runtime()

    def test_tactical_exclusions_use_index_contract(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'tests') as directory:
            root=Path(directory);db=sqlite3.connect(':memory:')
            db.executescript('create table metadata(key text primary key,value text);'
                             'create table samples(id integer primary key,payload text);'
                             'create table exposures(sample integer,position text);')
            db.execute('insert into metadata values(?,?)',('position_key_version','base-symmetry-opening-v2'))
            fixture='G1|w|8|4|4|0,0=wQ;1,0=bQ'
            translated='G1|w|8|4|4|20,30=wQ;21,30=bQ'
            db.execute('insert into samples values(1,?)',('{}',))
            db.execute('insert into exposures values(1,?)',(position_key(translated),))
            learning=SimpleNamespace(index_corpus=lambda *_:db,position_key=lambda _: 'wrong-legacy-key')
            with patch.object(gen2,'ROOT',root),patch.object(gen2,'tactical_keys',side_effect=lambda key:[key(fixture)]):
                result,_,removed=gen2.curated_index(learning,[],root/'index',root/'checkpoint')
                self.assertEqual(removed,1)
                self.assertEqual(result.execute('select count(*) from samples').fetchone()[0],0)
            db.close()

if __name__=='__main__':unittest.main()
