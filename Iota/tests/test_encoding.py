import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from common import ROOT,UhpProcess,command

class Encoding(unittest.TestCase):
    def test_chain_symmetries_and_divide(self):
        engine=UhpProcess([str(ROOT/'build/iota.exe')])
        try:
            command(engine,'newgame Base');rows,_=command(engine,'iota-divide 2')
            self.assertEqual(sum(int(x.split('\t')[1]) for x in rows),96)
            bugs=['Q','S1','S2','B1','B2','G1','G2','G3','A1','A2','A3']
            identities=[color+bug for bug in bugs for color in ('w','b')]
            canonical=None
            for reflection in range(2):
                for rotation in range(6):
                    cells=[]
                    for i,piece in enumerate(identities):
                        q,r=i,0
                        if reflection:q,r=r,q
                        for _ in range(rotation):q,r=-r,q+r
                        cells.append(f'{q},{r}={piece}')
                    command(engine,'iota-loadposition G1|w|22|11|11|'+';'.join(cells))
                    result,_=command(engine,'iota-canonical')
                    if canonical is None:canonical=result
                    self.assertEqual(result,canonical)
                    for architecture in ('cnn','gnn','cnn2','gnn2','cnn3'):
                        encoded,_=command(engine,'iota-encode '+architecture)
                        n=int(encoded[0].split()[0])
                        for row in encoded[n+1:]:
                            self.assertGreaterEqual(int(row.split()[2]),0)
            error,_=engine.command('bestmove time nonsense')
            self.assertTrue(error[0].startswith('err '))
        finally:engine.close()

if __name__=='__main__':unittest.main()
