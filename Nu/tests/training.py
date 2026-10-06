"""Packed feature sums must preserve forward values and training gradients."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import torch
from train import pooled_transform
torch.set_num_threads(1)
torch.manual_seed(1701)
rows=[[],[1,1,2],[3],[1,2],[],[4,5,4],[6],[7,2]]
flat=[];offsets=[0]
for ids in rows:flat.extend(ids);offsets.append(len(flat))
weight=torch.randn(12,8,requires_grad=True);bias=torch.randn(8,requires_grad=True)
packed=pooled_transform(torch.tensor(flat),torch.tensor(offsets),weight,8,bias)
reference=torch.stack([weight[ids].sum(0) if ids else weight.sum(0)*0 for ids in rows]).reshape(-1,2,8)+bias
torch.testing.assert_close(packed,reference)
first=torch.autograd.grad(packed.square().sum(),(weight,bias),retain_graph=True)
second=torch.autograd.grad(reference.square().sum(),(weight,bias))
for a,b in zip(first,second):torch.testing.assert_close(a,b)
print('Packed feature forward/gradient equivalence passed')
