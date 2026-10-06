"""Sequential fixed-depth comparisons on identical deterministic positions."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from genseki.uhp import UhpProcess

def command(engine,text):
    lines, elapsed = engine.command(text,120)
    assert not any(x.startswith('err') for x in lines),lines
    return lines,elapsed

def measure(executable,model,positions,depth):
    engine=UhpProcess([str(executable),'--model',str(model)])
    rows=[]
    try:
        for game in positions:
            command(engine,'newgame '+game)
            move,elapsed=command(engine,f'bestmove depth {depth}')
            info,_=command(engine,'nu-searchinfo');fields=info[0].split()
            assert int(fields[1])==depth,'incomplete fixed-depth measurement'
            rows.append(dict(move=move[0],seconds=elapsed,nodes=int(fields[3]),score=int(fields[5])))
    finally:engine.close()
    return rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--before',type=Path,required=True);p.add_argument('--after',type=Path,required=True)
    p.add_argument('--model',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--depth',type=int,default=2)
    args=p.parse_args();rng=random.Random(823)
    engine=UhpProcess([str(args.before),'--model',str(args.model)])
    positions=[]
    try:
        command(engine,'newgame Base');game='Base'
        for ply in range(21):
            if ply in (0,4,8,12,16,20):positions.append(game)
            legal,_=command(engine,'validmoves');moves=legal[0].split(';')
            game=command(engine,'play '+rng.choice(moves))[0][0]
            if game.split(';')[1]!='InProgress':break
    finally:engine.close()
    before=measure(args.before,args.model,positions,args.depth);after=measure(args.after,args.model,positions,args.depth)
    assert all(a['score']==b['score'] for a,b in zip(before,after)),'search score regression'
    report=dict(positions=positions,before=before,after=after,
                before_sha256=hashlib.sha256(args.before.read_bytes()).hexdigest(),
                after_sha256=hashlib.sha256(args.after.read_bytes()).hexdigest(),
                speedup=sum(x['seconds'] for x in before)/sum(x['seconds'] for x in after))
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(speedup=report['speedup'],scores_identical=True,positions=len(positions))))
if __name__=='__main__':main()
