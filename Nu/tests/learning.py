"""Leakage, nonlinear symmetry, bounded accumulation and exact CPU resume checks."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'Nu/tools'))
import learning

def args(data, output, index, wall=0):
    return argparse.Namespace(data=[data],data_manifest=None,index=index,output=output,device='cpu',seed=1701,
        batch=4,accumulation=2,widths=[64],heads=['nonlinear'],epochs=2,learning_rate=.001,
        ablate=None,outcome_only=False,initialize=None,wall_seconds=wall)

def main():
    import torch
    torch.set_num_threads(1)
    decisions=[dict(mover=1,alternatives=[dict(cp=100),dict(cp=40)]),
               dict(mover=-1,alternatives=[dict(cp=-100),dict(cp=-40)])]
    measured=learning.decision_metrics(decisions,[[0,1],[0,-1]])
    assert measured==dict(decisions=2,regret_cp=60,top_choice_agreement=0)
    assert learning.decision_metrics(decisions,[[1,0],[-1,0]])['top_choice_agreement']==1
    net=learning.make_network(64,'nonlinear',4)
    ids=torch.tensor([1,2,3,4,5]);offsets=torch.tensor([0,2,5])
    own=net(ids,offsets);swap=net(torch.tensor([3,4,5,1,2]),torch.tensor([0,3,5]))
    assert torch.equal(own,-swap)
    (own.sum()).backward();assert net.head.weight.grad is not None
    work=ROOT/'Nu/work';work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=work) as directory:
        base=Path(directory);data=base/'data.jsonl';rows=[]
        families={}
        for split in (0,1):
            families[split]=next(f'family-{i}' for i in range(100) if (int(hashlib.sha256(f'family-{i}'.encode()).hexdigest()[:8],16)%5==0)==bool(split))
        for i in range(32):
            split=i%2
            rows.append(dict(game=i,source='unit',seed=17,opening_family=families[split],ply=8,feature_schema=4,
                features=[[i+1,7000],[i+100,7128]],position=f'G1|w|8|4|4|{i},0=wQ;{i+1},0=bQ',
                teacher_search_cp=100 if split else -100,outcome=None,termination='ply_cap'))
        rows[1]['position']=rows[0]['position']
        # A ranking child crossing into held-out positions must remove its training parent.
        rows[2]['preferred_position']=rows[3]['position'];rows[2]['preferred_features']=rows[3]['features']
        rows[2]['alternative_position']=rows[2]['position'];rows[2]['alternative_features']=rows[2]['features'];rows[2]['mover']=1
        data.write_text(''.join(json.dumps(row)+'\n' for row in rows))
        db=learning.index_corpus([data],base/'index.sqlite')
        surviving={r[0] for r in db.execute('select position from samples')}
        assert learning.position_key(rows[0]['position']) not in surviving
        assert learning.position_key(rows[2]['position']) not in surviving
        assert learning.position_key(rows[3]['position']) not in surviving
        db.close()
        assert learning.run(args(data,base/'whole',base/'index.sqlite'))
        assert not learning.run(args(data,base/'resume',base/'index.sqlite',.00001))
        assert learning.run(args(data,base/'resume',base/'index.sqlite'))
        whole=torch.load(base/'whole/nu-64-nonlinear.pt',weights_only=True)
        resumed=torch.load(base/'resume/nu-64-nonlinear.pt',weights_only=True)
        assert all(torch.equal(value,resumed['state'][name]) for name,value in whole['state'].items())
        assert (base/'whole/nu-64-nonlinear.nnue').read_bytes()==(base/'resume/nu-64-nonlinear.nnue').read_bytes()
    print('Nu leakage/symmetry/accumulation/resume tests passed')

if __name__=='__main__':main()
