"""All twelve axial isometries, including legal-action target permutations."""
def transform(q,r,rotation=0,reflection=False):
    if not 0<=rotation<6:raise ValueError('invalid rotation')
    if reflection:q,r=r,q
    for _ in range(rotation):q,r=-r,q+r
    return q,r


def transform_position(position,rotation=0,reflection=False):
    fields=position.split('|')
    if len(fields)!=6 or fields[0]!='G1':raise ValueError('invalid position')
    stacks=[]
    for stack in fields[5].split(';') if fields[5] else []:
        cell,pieces=stack.split('=');q,r=transform(*map(int,cell.split(',')),rotation,reflection)
        stacks.append((q,r,pieces))
    fields[5]=';'.join(f'{q},{r}={pieces}' for q,r,pieces in sorted(stacks))
    return '|'.join(fields)


def action_permutation(before,after,rotation,reflection):
    transformed=[]
    for text in before:
        key=list(map(int,text.split()))
        if len(key)!=8:raise ValueError('invalid action identity')
        if key[0]!=2:
            if key[4]!=99999:key[4:6]=transform(*key[4:6],rotation,reflection)
            key[6:8]=transform(*key[6:8],rotation,reflection)
        transformed.append(tuple(key))
    lookup={tuple(map(int,text.split())):i for i,text in enumerate(after)}
    if len(lookup)!=len(after) or set(transformed)!=set(lookup):raise ValueError('symmetry legal-action mismatch')
    return [lookup[key] for key in transformed]


def remap_targets(row,permutation):
    result=dict(row)
    for field in ('policy','tactics'):
        if row.get(field) is not None:
            if len(row[field])!=len(permutation):raise ValueError('target length mismatch')
            values=[None]*len(permutation)
            for old,new in enumerate(permutation):values[new]=row[field][old]
            result[field]=values
    if 'alternatives' in row:result['alternatives']=[[permutation[i],s] for i,s in row['alternatives']]
    return result
