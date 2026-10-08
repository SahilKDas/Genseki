"""Completed frozen arena resume must skip every engine and reject mismatches."""
import argparse,json,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import arena
p=argparse.ArgumentParser()
for name in ('report','engine','model','opponent','opponent-model'):p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args();original=sys.argv
saved=json.loads(a.report.read_text());assert saved['completed'] and len(saved['games'])==saved['expected_games']
def invoke(output,threads=1):
 try:
  sys.argv=['arena.py','--engine',str(a.engine),'--model',str(a.model),'--opponent',str(a.opponent),'--opponent-model',str(a.opponent_model),
    '--output',str(output),'--resume','--games',str(saved['expected_games']),'--milliseconds',str(saved['milliseconds']),
    '--cap',str(saved['cap']),'--threads',str(threads),'--seed-base',str(saved['seed_base'])]
  arena.main()
 finally:sys.argv=original
with tempfile.TemporaryDirectory(dir=arena.ROOT/'Nu/work') as directory:
 output=Path(directory)/'arena.json';output.write_text(json.dumps(saved))
 invoke(output,saved['threads']);resumed=json.loads(output.read_text())
 assert resumed['games']==saved['games'] and resumed['points']==saved['points'] and resumed['completed']
 before=output.read_bytes()
 try:invoke(output,2 if saved['threads']==1 else 1)
 except RuntimeError:pass
 else:raise AssertionError('changed settings accepted')
 assert output.read_bytes()==before
 broken=dict(saved,engine_sha256='0'*64);output.write_text(json.dumps(broken));before=output.read_bytes()
 try:invoke(output,saved['threads'])
 except RuntimeError:pass
 else:raise AssertionError('changed binary accepted')
 assert output.read_bytes()==before
print('Nu completed-arena resume, artifact mismatch and settings tests passed')
