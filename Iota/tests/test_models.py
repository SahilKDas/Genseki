import sys
import unittest
from pathlib import Path
import tempfile
import torch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from models import Network, parse_encoding
from common import ROOT,UhpProcess,command

class Models(unittest.TestCase):
    def test_export_native(self):
        torch.set_num_threads(1)
        for architecture,width,blocks in (('cnn',32,4),('gnn',32,4),('cnn',64,6),('gnn',64,6)):
            torch.manual_seed(1701)
            net=Network(architecture,width,blocks)
            with tempfile.TemporaryDirectory(dir=ROOT/'work') as d:
                path=Path(d)/'model.iota';net.export(path)
                engine=UhpProcess([str(ROOT/'build/iota.exe'),'--model',str(path)])
                try:
                    for game in ('Base','Base;InProgress;White[2];wA1;bS1 /wA1'):
                        command(engine,'newgame '+game)
                        lines,_=command(engine,'iota-encode '+architecture)
                        with torch.no_grad(): value,policy=net(*parse_encoding(lines))
                        actual,_=command(engine,'iota-eval',30)
                        head=list(map(float,actual[0].split()));wdl=value.softmax(0)
                        self.assertLess(abs(head[0]-float(wdl[0]-wdl[2])),2e-5)
                        for a,b in zip(head[1:],wdl):self.assertLess(abs(a-float(b)),2e-5)
                        self.assertEqual(len(actual)-1,len(policy))
                        for a,b in zip(actual[1:],policy):self.assertLess(abs(float(a)-float(b)),2e-4)
                    for mode in ('alphabeta','mcts'):
                        command(engine,'options set Search '+mode)
                        valid,_=command(engine,'validmoves')
                        best,elapsed=command(engine,'bestmove time 00:00:00.250',2)
                        self.assertIn(best[0],valid[0].split(';'));self.assertLess(elapsed,.35)
                    command(engine,'play '+best[0]);command(engine,'undo')
                    before,_=command(engine,'iota-eval',30)
                    command(engine,'options set Threads 4')
                    after,_=command(engine,'iota-eval',30)
                    self.assertEqual(before,after)
                    error,_=engine.command('options set Threads 13')
                    self.assertTrue(error[0].startswith('err '))
                    original=path.read_bytes();path.write_bytes(original[:-1])
                    error,_=engine.command('options set Model '+str(path))
                    self.assertTrue(error[0].startswith('err '));path.write_bytes(original)
                finally:engine.close()

    def test_graph_permutation(self):
        net=Network('gnn');x=torch.randn(7,80);edges=torch.full((7,6),-1,dtype=torch.long)
        for i in range(6):edges[i,0]=i+1;edges[i+1,3]=i
        source=torch.tensor([0,-1]);dest=torch.tensor([6,1]);actions=torch.randn(2,16)
        v,p=net(x,edges,source,dest,actions)
        perm=torch.tensor([3,1,6,0,5,2,4]);inv=perm.argsort();mapped=torch.where(edges[perm]>=0,inv[edges[perm].clamp_min(0)],-1)
        v2,p2=net(x[perm],mapped,torch.where(source>=0,inv[source.clamp_min(0)],-1),inv[dest],actions)
        torch.testing.assert_close(v,v2);torch.testing.assert_close(p,p2)

if __name__=='__main__':
    (ROOT/'work').mkdir(exist_ok=True)
    unittest.main()
