"""Reference operators, bounded training, and checked native export for Iota."""
from __future__ import annotations
import hashlib
import struct
from pathlib import Path
import numpy as np
import torch
from torch import nn

FEATURES, ACTION = 80, 16

class Network(nn.Module):
    def __init__(self, architecture='gnn', width=32, blocks=4, version=1):
        super().__init__()
        if architecture not in ('cnn','gnn') or width not in (32,64) or blocks not in (4,6):
            raise ValueError('unsupported architecture')
        if version not in (1,2,3) or (version==3 and architecture!='cnn'): raise ValueError('unsupported representation version')
        self.architecture, self.width, self.blocks, self.version = architecture, width, blocks, version
        self.relations = 6 if version==3 else 1 if architecture=='cnn' else 5
        count = 7 if version==1 else self.relations+1
        self.input = nn.Linear(FEATURES, width)
        self.kernels = nn.ParameterList([nn.Parameter(torch.randn(count, width, width)*.02)
                                        for _ in range(blocks)])
        self.biases = nn.ParameterList([nn.Parameter(torch.zeros(width)) for _ in range(blocks)])
        self.value = nn.Linear(width, 3)
        self.policy = nn.Linear(3*width+ACTION, 1)

    def forward(self, x, edges, source, destination, actions):
        # One graph/grid per call; training streams microbatches and accumulates gradients.
        h = torch.relu(self.input(x))
        for kernel, bias in zip(self.kernels, self.biases):
            result = h @ kernel[0].T
            if self.version==1:
                for d in range(6):
                    idx = edges[:, d]
                    result = result + (h[idx.clamp_min(0)] @ kernel[d+1].T)*(idx >= 0)[:, None]
                divisor=7
            else:
                for relation in range(self.relations):
                    links=edges[edges[:,2]==relation]
                    aggregate=torch.zeros_like(h).index_add(0,links[:,0],h[links[:,1]])
                    degree=torch.zeros(len(h),device=h.device).index_add(0,links[:,0],torch.ones(len(links),device=h.device))
                    messages=aggregate if self.architecture=='cnn' else aggregate/degree.clamp_min(1)[:,None]
                    result=result+messages @ kernel[relation+1].T
                divisor=7 if self.architecture=='cnn' else self.relations+1
            h = torch.relu(h+(result+bias)/divisor)
        pooled = h.mean(0)
        src = h[source.clamp_min(0)]*(source >= 0)[:, None]
        dst = h[destination.clamp_min(0)]*(destination >= 0)[:, None]
        logits = self.policy(torch.cat((pooled.expand(len(actions), -1), src, dst, actions), 1))[:, 0]
        return self.value(pooled), logits

    def export(self, path):
        if any(not torch.isfinite(t).all().item() for t in self.parameters()):
            raise ValueError('nonfinite model weights')
        tensors = [self.input.weight, self.input.bias]
        for kernel, bias in zip(self.kernels, self.biases):
            tensors += [kernel, bias]
        tensors += [self.value.weight, self.value.bias, self.policy.weight, self.policy.bias]
        payload = b''.join(t.detach().cpu().numpy().astype('<f4').tobytes() for t in tensors)
        checksum = 1469598103934665603
        for byte in payload:
            checksum = ((checksum ^ byte)*1099511628211) & ((1 << 64)-1)
        data = struct.pack('<6IQ', 0x41544F49, self.version, int(self.architecture == 'gnn'),
                           self.width, self.blocks, len(payload)//4, checksum)+payload
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix+'.tmp')
        temp.write_bytes(data)
        temp.replace(path)
        return hashlib.sha256(data).hexdigest()

def parse_encoding(lines, device='cpu'):
    header=list(map(int,lines[0].split()))
    if len(header) not in (2,4): raise ValueError('invalid encoding header')
    n,f=header[:2];modern=len(header)==4
    if modern and (header[2]!=2 or header[3]<0):raise ValueError('invalid representation version')
    edge_count=header[3] if modern else 0
    rows = np.array([list(map(float, row.split())) for row in lines[1:n+1]], dtype=np.float32)
    action_lines=lines[n+1+edge_count:]
    if any(not row.startswith('action ') for row in action_lines):raise ValueError('invalid action row')
    acts = np.array([list(map(float, row.split()[1:])) for row in action_lines], dtype=np.float32)
    if f != FEATURES or acts.ndim != 2 or len(acts) == 0:
        raise ValueError('invalid or terminal encoding')
    if n<1 or rows.shape!=(n,2+FEATURES+(0 if modern else 6)) or acts.shape[1]!=2+ACTION:
        raise ValueError('encoding dimensions mismatch')
    if not np.isfinite(rows).all() or not np.isfinite(acts).all():
        raise ValueError('nonfinite encoding')
    if modern:
        edge_lines=lines[n+1:n+1+edge_count]
        if len(edge_lines)!=edge_count or any(not row.startswith('edge ') for row in edge_lines):raise ValueError('invalid edge rows')
        edges=np.array([list(map(int,row.split()[1:])) for row in edge_lines],dtype=np.int64).reshape(-1,3)
        if (edges[:,:2]<0).any() or (edges[:,:2]>=n).any() or (edges[:,2]<0).any() or (edges[:,2]>5).any():raise ValueError('invalid typed edge')
        indices=edges[:,:2]
    else:indices=rows[:,2+f:];edges=indices
    action_indices=acts[:,:2]
    if (indices!=np.floor(indices)).any() or (action_indices!=np.floor(action_indices)).any():
        raise ValueError('nonintegral node index')
    if (indices < -1).any() or (indices >= n).any() or (action_indices < -1).any() or (action_indices >= n).any():
        raise ValueError('node index outside encoding')
    return (torch.tensor(rows[:, 2:2+f], device=device),
            torch.tensor(edges, dtype=torch.long, device=device),
            torch.tensor(acts[:, 0], dtype=torch.long, device=device),
            torch.tensor(acts[:, 1], dtype=torch.long, device=device),
            torch.tensor(acts[:, 2:], device=device))
