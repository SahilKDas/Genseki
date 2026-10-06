"""Legal-action supervision and frozen-teacher distillation, without score fallbacks."""
import json
import math
from pathlib import Path
import torch
from torch.nn import functional as F


def distribution(values, size, device):
    target=torch.as_tensor(values, dtype=torch.float32, device=device)
    if target.shape!=(size,) or not torch.isfinite(target).all() or (target<0).any():
        raise ValueError('invalid probability target')
    if abs(float(target.sum())-1)>1e-4:raise ValueError('probability target must sum to one')
    return target


def supervised_loss(value, policy, row, ranking_weight=.25, tactical_weight=.5):
    terms=[]
    if row.get('policy') is not None:
        target=distribution(row['policy'],len(policy),policy.device)
        terms.append(-(target*F.log_softmax(policy,0)).sum())
    if row.get('wdl') is not None:
        target=distribution(row['wdl'],3,value.device)
        terms.append(-(target*F.log_softmax(value,0)).sum())
    if row.get('search_value') is not None:
        score=row['search_value']
        if not math.isfinite(score) or not -1<=score<=1:raise ValueError('invalid side-to-move search target')
        probabilities=value.softmax(0)
        terms.append(.25*F.smooth_l1_loss(probabilities[0]-probabilities[2],value.new_tensor(score)))
    alternatives=row.get('alternatives',[])
    seen=set()
    for index,score in alternatives:
        if not isinstance(index,int) or not 0<=index<len(policy) or index in seen or not math.isfinite(score):
            raise ValueError('invalid partial alternative ranking')
        seen.add(index)
    pairs=[]
    for i,a in alternatives:
        for j,b in alternatives:
            if a>b+.02:pairs.append(F.softplus(-(policy[i]-policy[j])))
    if pairs:terms.append(ranking_weight*torch.stack(pairs).mean())
    tactics=row.get('tactics',[])
    if tactics:
        if len(tactics)!=len(policy) or any(len(t)!=4 or any(x not in (0,1) for x in t) for t in tactics):
            raise ValueError('tactical labels must match the complete legal list')
        wins=[i for i,t in enumerate(tactics) if t[0]]
        safe=[i for i,t in enumerate(tactics) if not t[1]]
        # No preference is invented when every reply is safe or every reply loses.
        required=wins or (safe if len(safe)<len(policy) else [])
        if required:terms.append(-tactical_weight*torch.logsumexp(F.log_softmax(policy,0)[required],0))
    if not terms:raise ValueError('example has no usable supervision')
    return sum(terms)


def distillation_loss(student, teacher, temperature=2., value_mode='wdl'):
    if not math.isfinite(temperature) or temperature<=0:raise ValueError('invalid distillation temperature')
    sv,sp=student;tv,tp=teacher
    if sv.shape!=tv.shape or sp.shape!=tp.shape:raise ValueError('teacher/student action mismatch')
    if value_mode not in ('wdl','score','none'):raise ValueError('unknown teacher value supervision')
    terms=[F.kl_div(F.log_softmax(sp/temperature,0),F.softmax(tp.detach()/temperature,0),reduction='sum')*temperature**2]
    if value_mode=='wdl':terms.append(F.kl_div(F.log_softmax(sv/temperature,0),F.softmax(tv.detach()/temperature,0),reduction='sum')*temperature**2)
    elif value_mode=='score':
        s=sv.softmax(0);t=tv.detach().softmax(0)
        terms.append(F.smooth_l1_loss(s[0]-s[2],t[0]-t[2]))
    return sum(terms)


class Corpus:
    """Index positions on disk; do not copy the corpus into training RAM."""
    def __init__(self,path):
        self.path=Path(path);self.splits={'train':[], 'validation':[], 'test':[]};self.tactical=[]
        self.supervision={key:0 for key in ('policy','wdl','search_value','alternatives','tactics')}
        games={};families={};positions={}
        with self.path.open('rb') as stream:
            while True:
                offset=stream.tell();line=stream.readline()
                if not line:break
                row=json.loads(line);split=row['split']
                if split not in self.splits:raise ValueError('unknown corpus split')
                for groups,key in ((games,row['game_id']),(families,row.get('opening_family')),(positions,row['canonical'])):
                    if key is None:continue
                    if key in groups and groups[key]!=split:raise ValueError('cross-split game/family/transposition leakage')
                    groups[key]=split
                self.splits[split].append(offset)
                if split=='train':
                    for key in self.supervision:
                        if row.get(key) is not None and (key in ('wdl','search_value','policy') or bool(row[key])):self.supervision[key]+=1
                if split=='train' and any(any(t) for t in row.get('tactics',[])):self.tactical.append(offset)
    def row(self,offset):
        with self.path.open('rb') as stream:stream.seek(offset);return json.loads(stream.readline())
