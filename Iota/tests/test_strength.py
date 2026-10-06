import json
import sys
import tempfile
import unittest
from pathlib import Path
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from models import Network,parse_encoding
from common import ROOT,UhpProcess,command
from symmetry import transform_position,action_permutation,remap_targets
from learning import Corpus,supervised_loss,distillation_loss

STACK='G1|w|8|4|4|-1,0=wA1;0,-1=bA1;0,0=wQ,bB1;1,-1=wB1;1,0=bQ'


class Strength(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(1);(ROOT/'work').mkdir(exist_ok=True)

    def test_stones_relations_and_covered_queen(self):
        engine=UhpProcess([str(ROOT/'build/iota.exe')])
        try:
            command(engine,'newgame Base');command(engine,'iota-loadposition '+STACK)
            lines,_=command(engine,'iota-encode gnn2');x,edges,src,dst,actions=parse_encoding(lines)
            self.assertEqual(int(x[:,1].sum()),6)
            self.assertEqual(int(x[:,63].sum()),1)
            self.assertEqual(int(((x[:,53]==1)&(x[:,63]==1)).sum()),1)
            relations=set(edges[:,2].tolist());self.assertTrue({0,1,2,3,4}.issubset(relations))
            self.assertTrue((dst>=0).all())
            for a,b,r in edges.tolist():
                if r==1:self.assertIn([b,a,2],edges.tolist())
            covered=int(torch.where((x[:,53]==1)&(x[:,63]==1))[0][0])
            self.assertNotIn(covered,src.tolist())
        finally:engine.close()

    def test_all_symmetries_policy_and_native_agreement(self):
        for architecture in ('cnn','gnn'):
            torch.manual_seed(73);net=Network(architecture,32,4,2)
            with tempfile.TemporaryDirectory(dir=ROOT/'work') as directory:
                path=Path(directory)/'v2.iota';net.export(path)
                engine=UhpProcess([str(ROOT/'build/iota.exe'),'--model',str(path)])
                try:
                    command(engine,'newgame Base');command(engine,'iota-loadposition '+STACK)
                    before,_=command(engine,'iota-actions')
                    encoded,_=command(engine,'iota-encode '+architecture+'2')
                    with torch.no_grad():value,policy=net(*parse_encoding(encoded))
                    for reflection in (False,True):
                        for rotation in range(6):
                            command(engine,'iota-loadposition '+transform_position(STACK,rotation,reflection))
                            after,_=command(engine,'iota-actions');perm=action_permutation(before,after,rotation,reflection)
                            encoded,_=command(engine,'iota-encode '+architecture+'2')
                            with torch.no_grad():v,p=net(*parse_encoding(encoded))
                            torch.testing.assert_close(v,value,atol=2e-5,rtol=2e-5)
                            torch.testing.assert_close(p[perm],policy,atol=2e-5,rtol=2e-5)
                            actual,_=command(engine,'iota-eval',30)
                            wdl=v.softmax(0);head=list(map(float,actual[0].split()))
                            self.assertAlmostEqual(head[0],float(wdl[0]-wdl[2]),places=5)
                            torch.testing.assert_close(torch.tensor(list(map(float,actual[1:]))),p,atol=2e-4,rtol=2e-4)
                finally:engine.close()

    def test_tactical_and_ranking_gradients(self):
        value=torch.zeros(3,requires_grad=True);policy=torch.zeros(3,requires_grad=True)
        row=dict(policy=[.7,.2,.1],wdl=None,alternatives=[[0,.8],[1,-.5]],
                 tactics=[[1,0,0,0],[0,1,0,0],[0,0,1,1]])
        loss=supervised_loss(value,policy,row);loss.backward()
        self.assertLess(float(policy.grad[0]),float(policy.grad[1]))
        distillation_loss((value,policy),(torch.tensor([2.,0.,-1.]),torch.tensor([3.,1.,0.]))).backward()
        self.assertTrue(torch.isfinite(policy.grad).all())
        for bad in ([.5,.5],[-1.,1.,1.],[0.,0.,0.]):
            with self.assertRaises(ValueError):supervised_loss(value,policy,dict(policy=bad))

    def test_exact_wins_and_mandatory_defenses(self):
        positions=[
            'G1|w|14|7|7|-2,1=wA1;-1,0=wQ;-1,1=wB1;0,-1=bA1;0,0=bQ;1,-1=wS1;1,0=bS1',
            'G1|w|14|7|7|-2,1=bA1;-1,0=bQ;-1,1=bB1;0,-1=bS2;0,0=wQ;1,-1=bS1;1,0=wB1']
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as directory:
            path=Path(directory)/'model.iota';Network('gnn',32,4,2).export(path)
            engine=UhpProcess([str(ROOT/'build/iota.exe'),'--model',str(path)])
            try:
                command(engine,'newgame Base')
                for case,position in enumerate(positions):
                    command(engine,'iota-loadposition '+position)
                    lines,_=command(engine,'iota-tactics 2000',3)
                    labels=[list(map(int,line.split()[1:])) for line in lines]
                    legal,_=command(engine,'validmoves');moves=legal[0].split(';')
                    self.assertEqual(len(labels),len(moves))
                    if case==0:self.assertTrue(any(t[0] for t in labels))
                    else:
                        self.assertTrue(any(t[1] for t in labels));self.assertTrue(any(not t[1] for t in labels))
                    for index,(move,tactic) in enumerate(zip(moves,labels)):
                        command(engine,'iota-loadposition '+position);command(engine,'iota-playindex '+str(index))
                        result=command(engine,'iota-result')[0][0]
                        self.assertEqual(bool(tactic[0]),result=='white-win')
                        unsafe=False
                        if result=='ongoing':
                            replies,_=command(engine,'validmoves')
                            for j,reply in enumerate(replies[0].split(';')):
                                command(engine,'iota-playindex '+str(j));outcome,_=command(engine,'iota-result')
                                unsafe=unsafe or outcome[0]=='black-win'
                                command(engine,'undo')
                        self.assertEqual(bool(tactic[1]),unsafe)
                        command(engine,'undo');restored,_=command(engine,'iota-position')
                        self.assertEqual(restored[0],position)
            finally:engine.close()

    def test_v2_large_exports_permutation_and_visit_targets(self):
        for architecture in ('cnn','gnn'):
            net=Network(architecture,64,6,2)
            with tempfile.TemporaryDirectory(dir=ROOT/'work') as directory:
                path=Path(directory)/'large.iota';net.export(path)
                engine=UhpProcess([str(ROOT/'build/iota.exe'),'--model',str(path)])
                try:
                    command(engine,'newgame Base')
                    encoded,_=command(engine,'iota-encode '+architecture+'2');inputs=parse_encoding(encoded)
                    with torch.no_grad():v,p=net(*inputs)
                    actual,_=command(engine,'iota-eval',30)
                    self.assertAlmostEqual(float(actual[0].split()[0]),float(v.softmax(0)[0]-v.softmax(0)[2]),places=5)
                    torch.testing.assert_close(torch.tensor(list(map(float,actual[1:]))),p,atol=2e-4,rtol=2e-4)
                    if architecture=='gnn':
                        x,edges,src,dst,actions=inputs
                        # A nontrivial node permutation on a stacked position.
                        command(engine,'iota-loadposition '+STACK);enc,_=command(engine,'iota-encode gnn2')
                        x,edges,src,dst,actions=parse_encoding(enc);perm=torch.randperm(len(x));inv=perm.argsort()
                        mapped=edges.clone();mapped[:,:2]=inv[edges[:,:2]]
                        with torch.no_grad():
                            v,p=net(x,edges,src,dst,actions)
                            v2,p2=net(x[perm],mapped,torch.where(src>=0,inv[src.clamp_min(0)],-1),inv[dst],actions)
                        torch.testing.assert_close(v,v2);torch.testing.assert_close(p,p2)
                        command(engine,'newgame Base');command(engine,'options set Search mcts')
                        command(engine,'bestmove time 00:00:00.200',2)
                        target,_=command(engine,'iota-searchinfo');self.assertGreaterEqual(int(target[0].split()[1]),2)
                        self.assertAlmostEqual(sum(map(float,target[1:])),1.,places=4)
                        command(engine,'play wA1')
                        error,_=engine.command('iota-searchinfo');self.assertTrue(error[0].startswith('err '))
                finally:engine.close()

    def test_distillation_across_architectures(self):
        teacher=Network('gnn',64,6,2).eval();teacher.requires_grad_(False)
        student=Network('cnn',32,4,2)
        engine=UhpProcess([str(ROOT/'build/iota.exe')])
        try:
            command(engine,'newgame Base')
            graph,_=command(engine,'iota-encode gnn2');grid,_=command(engine,'iota-encode cnn2')
            with torch.no_grad():target=teacher(*parse_encoding(graph))
            prediction=student(*parse_encoding(grid));loss=distillation_loss(prediction,target);loss.backward()
            self.assertTrue(any(p.grad is not None and p.grad.abs().sum()>0 for p in student.parameters()))
            self.assertTrue(all(p.grad is None for p in teacher.parameters()))
        finally:engine.close()

    def test_untrained_teacher_value_is_not_distilled(self):
        value=torch.zeros(3,requires_grad=True);policy=torch.zeros(2,requires_grad=True)
        reference=(torch.tensor([50.,-50.,0.]),torch.tensor([1.,-1.]))
        distillation_loss((value,policy),reference,value_mode='none').backward()
        self.assertIsNone(value.grad);self.assertIsNotNone(policy.grad)

    def test_leakage_and_target_permutation(self):
        rows=[dict(game_id='1',canonical='same',opening_family='a',split='train'),
              dict(game_id='2',canonical='same',opening_family='b',split='validation')]
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as directory:
            path=Path(directory)/'corpus.jsonl';path.write_text('\n'.join(map(json.dumps,rows)))
            with self.assertRaises(ValueError):Corpus(path)
        row=dict(policy=[.7,.2,.1],tactics=[[1,0,0,0],[0,1,0,0],[0,0,0,1]],alternatives=[[0,.8]])
        mapped=remap_targets(row,[2,0,1]);self.assertEqual(mapped['policy'],[.2,.1,.7]);self.assertEqual(mapped['alternatives'],[[2,.8]])

    def test_pass_has_no_artificial_origin_endpoint(self):
        engine=UhpProcess([str(ROOT/'build/iota.exe')])
        try:
            command(engine,'newgame Base')
            command(engine,'iota-loadposition G1|w|8|4|4|0,0=wQ,bB1;1,0=bQ')
            legal,_=command(engine,'validmoves');self.assertEqual(legal,['pass'])
            for arch in ('cnn2','gnn2'):
                lines,_=command(engine,'iota-encode '+arch);_,_,src,dst,_=parse_encoding(lines)
                self.assertEqual(src.tolist(),[-1]);self.assertEqual(dst.tolist(),[-1])
        finally:engine.close()

    def test_tied_kernel_matches_untied_control_with_shared_weights(self):
        tied=Network('cnn',32,4,2);untied=Network('cnn',32,4,3)
        with torch.no_grad():
            for component in ('input','value','policy'):getattr(untied,component).load_state_dict(getattr(tied,component).state_dict())
            for a,b in zip(untied.biases,tied.biases):a.copy_(b)
            for a,b in zip(untied.kernels,tied.kernels):a[0].copy_(b[0]);a[1:].copy_(b[1].expand(6,-1,-1))
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as directory:
            path=Path(directory)/'control.iota';untied.export(path)
            engine=UhpProcess([str(ROOT/'build/iota.exe'),'--model',str(path)])
            try:
                command(engine,'newgame Base');command(engine,'iota-loadposition '+STACK)
                a,_=command(engine,'iota-encode cnn2');b,_=command(engine,'iota-encode cnn3')
                with torch.no_grad():v,p=tied(*parse_encoding(a));v2,p2=untied(*parse_encoding(b))
                torch.testing.assert_close(v,v2);torch.testing.assert_close(p,p2)
                actual,_=command(engine,'iota-eval',30)
                torch.testing.assert_close(torch.tensor(list(map(float,actual[1:]))),p2,atol=2e-4,rtol=2e-4)
            finally:engine.close()


if __name__=='__main__':unittest.main()
