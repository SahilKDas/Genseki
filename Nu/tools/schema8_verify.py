"""Independent integer inference and trained schema-7/8 search parity."""
import argparse
from array import array
from contextlib import ExitStack, closing
import json
from pathlib import Path
import random
import struct
import sys

from evidence import atomic_json, digest
from research_job import run
from train import resource_guard, response
from genseki.uhp import UhpProcess


def integer_reference(raw, features):
    width = struct.unpack_from('<I', raw, 16)[0]
    def read(code, offset, count):
        value = array(code);value.frombytes(raw[offset:offset+count*value.itemsize])
        if sys.byteorder != 'little':value.byteswap()
        return value
    bias = read('i', 32, width)
    embedding = read('h', 32+width*4, 8192*width)
    offset = 32+width*4+8192*width*2
    nonlinear = raw[:8] == b'NUNNUE2\0'
    if nonlinear:
        head = read('h', offset, 32*2*width);offset += 32*2*width*2
        head_bias = read('i', offset, 32);offset += 32*4
    output = read('h', offset, 32 if nonlinear else width)
    sums = [[bias[j]+sum(embedding[id*width+j] for id in features[p]) for j in range(width)] for p in [0,1]]
    clipped = [[max(0,min(256,value)) for value in bank] for bank in sums]
    if nonlinear:
        white = 0
        for j in range(32):
            activations = []
            for orientation in [0,1]:
                value = head_bias[j]*256+sum(clipped[p^orientation][k]*head[j*2*width+p*width+k] for p in [0,1] for k in range(width))
                activations.append(max(0,min(256,value//256)))
            white += (activations[0]-activations[1])*output[j]
    else:
        white = sum((clipped[0][j]-clipped[1][j])*output[j] for j in range(width))
    scaled = (1 if white >= 0 else -1)*(abs(white)*600//(65536*(2 if nonlinear else 1)))
    return max(-5000,min(5000,scaled))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, required=True)
    parser.add_argument('--schema7', type=Path, required=True)
    parser.add_argument('--schema8', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if args.report.exists():raise RuntimeError('refusing to overwrite verification evidence')
    raw = args.schema8.read_bytes();other = args.schema7.read_bytes()
    if raw[12:] != other[12:]:raise RuntimeError('checkpoint payloads differ')
    randomizer = random.Random(1701);positions=searches=0
    with ExitStack() as stack:
        peers = [stack.enter_context(closing(UhpProcess([str(args.engine.resolve()),'--model',str(model.resolve())]))) for model in [args.schema7,args.schema8]]
        for peer in peers:response(peer,'options Threads 1');response(peer,'options TableMiB 16')
        def check(search=False):
            nonlocal positions, searches
            resource_guard()
            lanes=[response(peer,'nu-features') for peer in peers]
            priors=[int(response(peer,'nu-prior')[0]) for peer in peers]
            boards=[response(peer,'nu-position')[0] for peer in peers]
            if lanes[0]!=lanes[1] or priors[0]!=priors[1] or boards[0]!=boards[1]:raise RuntimeError('trained feature/prior/score parity failed')
            features=[list(map(int,line.split(':')[1].split())) for line in lanes[1][:2]]
            expected=max(-6800,min(6800,integer_reference(raw,features)+priors[1]))
            if boards[1].split('|')[1]=='b':expected=-expected
            if int(lanes[1][2].split()[1])!=expected:raise RuntimeError('independent integer inference mismatch')
            if search:
                results=[]
                for peer in peers:
                    move=response(peer,'bestmove depthorseconds 2 5')
                    info=response(peer,'nu-searchinfo')
                    fields=info[0].split()
                    if int(fields[1])!=2 and not (int(fields[1])>0 and abs(int(fields[5]))>90000):raise RuntimeError('incomplete parity search')
                    results.append((move,info))
                if results[0]!=results[1]:raise RuntimeError('fixed-depth search parity failed')
                searches+=1
            positions+=1
        for fixture in ['G1|w|8|4|4|0,0=wQ,bB1;1,0=bQ','G1|b|8|4|4|0,0=wA1,bB1;1,0=wQ;2,0=bQ']:
            for peer in peers:response(peer,'nu-loadposition '+fixture)
            check(True)
        for game in range(4):
            for peer in peers:response(peer,'newgame Base')
            for ply in range(100):
                check(ply%8==0)
                moves=response(peers[0],'validmoves')[0].split(';')
                move=randomizer.choice(moves)
                games=[response(peer,'play '+move)[0] for peer in peers]
                if games[0]!=games[1]:raise RuntimeError('replay disagreement')
                if games[0].split(';')[1]!='InProgress':break
                if ply%7==0:
                    for peer in peers:response(peer,'undo')
                    check()
                    for peer in peers:response(peer,'play '+move)
    result={'version':1,'engine_sha256':digest(args.engine),'schema7_sha256':digest(args.schema7),
            'schema8_sha256':digest(args.schema8),'positions':positions,'fixed_depth_searches':searches,
            'features_prior_scores_nodes_pv_equal':True,'independent_integer_exact':True}
    atomic_json(args.report,result);print(json.dumps(result))


if __name__=='__main__':run(main)
