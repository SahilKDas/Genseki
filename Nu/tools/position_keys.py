"""Base Hive symmetry/identity normalized leakage keys (v1)."""
import hashlib
import json

def position_key(position):
    fields=position.split('|')
    if len(fields)!=6 or fields[0]!='G1':raise ValueError('expected G1 position')
    cells=[]
    for entry in fields[5].split(';'):
        if entry:
            xy,stack=entry.split('=')
            q,r=map(int,xy.split(','))
            cells.append((q,r,','.join(piece[:2] for piece in stack.split(','))))
    forms=[]
    for mirror in (False,True):
        transformed=[(r,q,s) if mirror else (q,r,s) for q,r,s in cells]
        for rotation in range(6):
            origin_q=min((q for q,r,s in transformed),default=0)
            origin_r=min((r for q,r,s in transformed),default=0)
            forms.append(sorted((q-origin_q,r-origin_r,s) for q,r,s in transformed))
            transformed=[(-r,q+r,s) for q,r,s in transformed]
    queens={piece[:2] for entry in fields[5].split(';') if entry for piece in entry.split('=')[1].split(',')}
    phase=[4 if color+'Q' in queens else min(int(fields[index]),4) for color,index in (('w',3),('b',4))]
    return hashlib.sha256(json.dumps([fields[1],phase,min(forms)],separators=(',',':')).encode()).hexdigest()

