"""Compare exported integer inference against native Nu and the float checkpoint."""
import argparse
import json
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from genseki.uhp import UhpProcess
from evidence import atomic_json, digest

def main():
    import numpy as np
    import torch
    parser = argparse.ArgumentParser()
    parser.add_argument('model', type=Path)
    parser.add_argument('--engine', type=Path, default=ROOT / 'build-nu/nu.exe')
    args = parser.parse_args()
    raw = args.model.read_bytes()
    width = struct.unpack_from('<I', raw, 16)[0]
    schema = struct.unpack_from('<I', raw, 8)[0]
    bias = np.frombuffer(raw, '<i4', width, 32).astype(np.int64)
    embedding = np.frombuffer(raw, '<i2', 8192 * width, 32 + width * 4).reshape(8192, width).astype(np.int64)
    at=32+width*4+8192*width*2
    nonlinear=raw[:8]==b'NUNNUE2\0'
    if nonlinear:
        head=np.frombuffer(raw,'<i2',32*2*width,at).reshape(32,2*width).astype(np.int64);at+=32*2*width*2
        head_bias=np.frombuffer(raw,'<i4',32,at).astype(np.int64);at+=32*4
    output = np.frombuffer(raw, '<i2', 32 if nonlinear else width, at).astype(np.int64)
    checkpoint = torch.load(args.model.with_suffix('.pt'), map_location='cpu', weights_only=True)['state']
    engine = UhpProcess([str(args.engine), '--model', str(args.model)])
    maximum = 0
    count = 0
    try:
        for game in range(4):
            engine.command('newgame Base')
            for ply in range(100):
                lines, _ = engine.command('nu-features')
                ids = [list(map(int, line.split(':')[1].split())) for line in lines[:2]]
                sums = [bias + embedding[index].sum(0) if index else bias.copy() for index in ids]
                clipped=[np.clip(total,0,256) for total in sums]
                if nonlinear:
                    pair=np.concatenate(clipped);swap=np.concatenate(clipped[::-1])
                    activations=[np.clip(np.trunc((head@value+head_bias*256)/256).astype(np.int64),0,256) for value in (pair,swap)]
                    white=int((activations[0]-activations[1])@output)
                else:white=int((clipped[0]-clipped[1])@output)
                prior = int(engine.command('nu-prior')[0][0]) if schema in (5,7) else 0
                expected_white = max(-6800,min(6800,max(-5000, min(5000, int(white * 600 / (65536*(2 if nonlinear else 1)))))+prior))
                expected = expected_white * (1 if ply % 2 == 0 else -1)
                native = int(lines[2].split()[1])
                assert native == expected, (native, expected)
                floats = [checkpoint['bias'] + checkpoint['embedding.weight'][index].sum(0) for index in ids]
                if nonlinear:
                    pair=torch.cat([value.clamp(0,1) for value in floats]);swap=torch.cat([value.clamp(0,1) for value in floats[::-1]])
                    activated=[torch.nn.functional.linear(value,checkpoint['head.weight'],checkpoint['head.bias']).clamp(0,1) for value in (pair,swap)]
                    reference=((activated[0]-activated[1])*checkpoint['output']).sum().item()*300
                else:reference = ((floats[0].clamp(0, 1) - floats[1].clamp(0, 1)) * checkpoint['output']).sum().item() * 600
                reference = max(-6800,min(6800,max(-5000,min(5000,reference))+prior))
                maximum = max(maximum, abs(reference - expected_white))
                count += 1
                moves, _ = engine.command('validmoves')
                if not moves[0]: break
                move = moves[0].split(';')[(ply * 17 + game) % len(moves[0].split(';'))]
                result, _ = engine.command('play ' + move)
                if result[0].split(';')[1] != 'InProgress': break
    finally:
        engine.close()
    report=dict(positions=count,native_integer_exact=True,maximum_float_error_cp=maximum,
                model_sha256=digest(args.model),engine_sha256=digest(args.engine))
    atomic_json(args.model.with_suffix('.verification.json'),report)
    print(json.dumps(report))

if __name__ == '__main__': main()
