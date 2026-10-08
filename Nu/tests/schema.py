"""Schema metadata and corpus compatibility without training or tensor allocation."""
import ast
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import tempfile
import unittest

TOOLS=Path(__file__).resolve().parents[1]/'tools'
WORK=TOOLS.parent/'work'
WORK.mkdir(exist_ok=True)
sys.path.insert(0,str(TOOLS))
import learning

class SchemaTests(unittest.TestCase):
    def test_bootstrap_records_actual_engine_schema(self):
        tree=ast.parse((TOOLS/'train.py').read_text())
        function=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=='corpus')
        class Engine:
            def __init__(self,invocation):pass
            def close(self):pass
        def response(engine,command):
            if command=='nu-feature-schema':return ['6']
            if command=='nu-features':return ['w: 1 7000','b: 2 7128','cp 0']
            if command.startswith('bestmove '):return ['wA1']
            if command=='nu-searchinfo':return ['depth 1 nodes 2 cp 3']
            if command=='nu-position':return ['G1|w|0|0|0|']
            if command=='newgame Base':return ['Base;NotStarted;White[1]']
            if command.startswith('play '):return ['Base;WhiteWins;Black[1]']
            raise AssertionError(command)
        namespace=dict(random=random,hashlib=hashlib,UhpProcess=Engine,response=response,
                       resource_guard=lambda:None,json=json,os=os)
        exec(compile(ast.Module(body=[function],type_ignores=[]),'bootstrap','exec'),namespace)
        with tempfile.TemporaryDirectory(dir=WORK) as directory:
            path=Path(directory)/'corpus.jsonl'
            rows=namespace['corpus'](Path('fixture'),path,1,1,1)
            self.assertEqual(rows[0]['feature_schema'],6)
            self.assertEqual(json.loads(path.read_text())['feature_schema'],6)

    def test_index_accepts_six_and_rejects_mixed_or_unknown(self):
        for versions in ([6],[4,6],[5],[7],[8]):
            with tempfile.TemporaryDirectory(dir=WORK) as directory:
                root=Path(directory);source=root/'corpus.jsonl'
                rows=[dict(source='unit',game=i,ply=0,feature_schema=version,
                           features=[[1],[2]],position=f'G1|w|2|1|1|{i},0=wA1;{i+1},0=bS1')
                      for i,version in enumerate(versions)]
                source.write_text('\n'.join(json.dumps(row) for row in rows))
                if versions==[6]:
                    db=learning.index_corpus([source],root/'index.db')
                    try:self.assertEqual(db.execute('select value from metadata where key="schema"').fetchone()[0],'6')
                    finally:db.close()
                else:
                    with self.assertRaisesRegex(RuntimeError,'mixed/unsupported|requires strategic prior'):
                        learning.index_corpus([source],root/'index.db')

if __name__=='__main__':unittest.main()
