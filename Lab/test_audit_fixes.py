"""Small regression checks without loading models or launching training jobs."""
import argparse
import ast
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import hashlib

ROOT = Path(__file__).resolve().parents[1]


def function(path, name, namespace):
    tree = ast.parse((ROOT / path).read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(path), 'exec'), namespace)
    return namespace[name]


class AuditFixTests(unittest.TestCase):
    def test_refeature_children_and_missing_coordinates(self):
        class Engine:
            position = None
            def close(self):
                pass
        def response(engine, command):
            if command == 'nu-feature-schema':
                return ['4']
            if command.startswith('nu-loadposition '):
                engine.position = command.split(' ', 1)[1]
                return []
            value = {'parent': 1, 'best': 2, 'other': 3}[engine.position]
            return [f'w: {value}', f'b: {value + 10}']
        main = function('Nu/tools/refeature.py', 'main', dict(
            argparse=argparse, json=json, Path=Path, response=response,
            UhpProcess=lambda _: Engine()))
        with tempfile.TemporaryDirectory(dir=ROOT/'Lab') as folder:
            source, output = Path(folder)/'in.jsonl', Path(folder)/'out.jsonl'
            source.write_text('\n'.join(json.dumps(row) for row in [
                dict(position='parent', features=[[99], [99]], feature_schema=2,
                     alternatives=[dict(position='best', features=[[99], [99]]),
                                   dict(position='other', features=[[99], [99]])]),
                dict(position='parent', alternatives=[dict(features=[[99], [99]])])]))
            with patch.object(sys, 'argv', ['refeature', '--engine', 'fake', '--input', str(source), '--output', str(output)]):
                main()
            rows = [json.loads(line) for line in output.read_text().splitlines()]
            self.assertEqual(rows[0]['feature_schema'], 4)
            self.assertEqual([c['features'] for c in rows[0]['alternatives']], [[[2], [12]], [[3], [13]]])
            self.assertNotIn('alternatives', rows[1])

    def holdout(self, checkpoint_exists):
        workspace = tempfile.TemporaryDirectory(dir=ROOT/'Lab')
        self.addCleanup(workspace.cleanup)
        db = sqlite3.connect(':memory:')
        db.executescript('create table samples(id integer,position text);'
                         'create table exposures(sample integer,position text);'
                         'create table metadata(key text,value text);'
                         "insert into samples values(1,'parent'),(2,'safe');"
                         "insert into exposures values(1,'heldout'),(2,'safe');")
        curate = function('Alpha/tools/gen2.py', 'curated_index', dict(
            ROOT=Path(workspace.name), hashlib=hashlib, json=json,
            tactical_keys=lambda _: ['heldout']))
        learning = SimpleNamespace(index_corpus=lambda *_: db, position_key=lambda p: p)
        return curate, db, learning, SimpleNamespace(exists=lambda: checkpoint_exists)

    def test_holdout_excludes_child(self):
        curate, db, learning, checkpoint = self.holdout(False)
        _, _, count = curate(learning, [], None, checkpoint)
        self.assertEqual(count, 1)
        self.assertEqual(db.execute('select id from samples').fetchall(), [(2,)])
        db.close()

    def test_holdout_rejects_existing_contaminated_checkpoint(self):
        curate, _, learning, checkpoint = self.holdout(True)
        with self.assertRaises(RuntimeError):
            curate(learning, [], None, checkpoint)

if __name__ == '__main__':
    unittest.main()
