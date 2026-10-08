"""Nu-only bootstrap: search targets plus separately recorded natural outcomes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import struct
import sys
import ctypes
import copy

def resource_guard():
    from research_job import check_deadline
    check_deadline()
    class Memory(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [(name, ctypes.c_ulonglong) for name in ('total', 'free', 'total_page', 'free_page', 'total_virtual', 'free_virtual', 'extended')]
    memory = Memory(); memory.length = ctypes.sizeof(memory)
    if os.name == 'nt':
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
            raise RuntimeError('cannot verify available RAM')
        if memory.free < 512 * 1024**2:
            raise RuntimeError('RAM reserve below 0.5 GiB; stopping safely')

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from genseki.uhp import UhpProcess

def pooled_transform(indices,offsets,weight,width,bias):
    import torch
    return torch.nn.functional.embedding_bag(indices,weight,offsets,mode='sum',
                                             include_last_offset=True).reshape(-1,2,width)+bias

def response(engine, text):
    from research_job import check_deadline
    check_deadline()
    lines, _ = engine.command(text)
    if any(line.startswith('err ') for line in lines):
        raise RuntimeError(lines)
    return [line for line in lines if line != 'ok']

def corpus(engine_path, output, games, cap, milliseconds, source_model=None):
    rng = random.Random(1701)
    invocation = [str(engine_path)] + (['--model', str(source_model)] if source_model else [])
    provenance = hashlib.sha256(source_model.read_bytes()).hexdigest() if source_model else 'untrained-seed-1701'
    engine = UhpProcess(invocation)
    records = []
    version=int(response(engine,'nu-feature-schema')[0])
    if version==5:
        engine.close();raise RuntimeError('schema 5 requires refeature.py and learning.py residual training')
    try:
        for game in range(games):
            resource_guard()
            response(engine, 'newgame Base')
            rows = []
            outcome = None
            for ply in range(cap):
                lines = response(engine, 'nu-features')
                active = [list(map(int, line.split(':')[1].split())) for line in lines[:2]]
                move = response(engine, f'bestmove depthorseconds 4 {milliseconds / 1000}')[0]
                info = response(engine, 'nu-searchinfo')[0].split()
                score = int(info[5]) * (1 if ply % 2 == 0 else -1)
                rows.append(dict(game=game, ply=ply, features=active, feature_schema=version, search_cp=score,
                                 depth=int(info[1]), nodes=int(info[3]),
                                 position=response(engine, 'nu-position')[0]))
                if rng.random() < .2:
                    move = rng.choice(response(engine, 'validmoves')[0].split(';'))
                game_string = response(engine, 'play ' + move)[0]
                result = game_string.split(';')[1]
                if result in ('WhiteWins', 'BlackWins', 'Draw'):
                    outcome = {'WhiteWins': 1, 'BlackWins': -1, 'Draw': 0}[result]
                    break
            for row in rows:
                row.update(outcome=outcome, termination='natural' if outcome is not None else 'ply_cap',
                           source=provenance, seed=1701)
            records.extend(rows)
            print(f'game {game + 1}/{games}: {len(rows)} plies, outcome={outcome}', flush=True)
    finally:
        engine.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.pending')
    temporary.write_text(''.join(json.dumps(row) + '\n' for row in records), encoding='utf8')
    os.replace(temporary, output)
    return records

def export(net, path):
    import numpy as np
    def quant(tensor, dtype):
        values = np.rint(tensor.detach().cpu().numpy() * 256)
        limit = np.iinfo(dtype)
        if values.min() < limit.min or values.max() > limit.max:
            raise RuntimeError('quantization overflow')
        return values.astype(dtype).tobytes()
    payload = quant(net.bias, '<i4') + quant(net.embedding.weight, '<i2')
    nonlinear=getattr(net,'head',None) is not None
    if nonlinear:payload+=quant(net.head.weight,'<i2')+quant(net.head.bias,'<i4')
    payload+=quant(net.output,'<i2')
    checksum = 14695981039346656037
    for byte in payload:
        checksum = ((checksum ^ byte) * 1099511628211) & ((1 << 64) - 1)
    header = struct.pack('<8sIIIIQ', b'NUNNUE2\0' if nonlinear else b'NUNNUE1\0', net.schema, 8192, net.width, 256, checksum)
    temporary = path.with_suffix('.pending')
    encoded=header+payload
    if path.exists():
        if path.read_bytes()!=encoded:raise RuntimeError('immutable model output already exists; choose a new candidate namespace')
        return
    temporary.write_bytes(encoded)
    os.replace(temporary, path)

def train(records, output, epochs, batch, device_name,widths=(64,128)):
    import torch
    from torch import nn
    versions={row.get('feature_schema',1) for row in records}
    if not records or len(versions)!=1 or not versions.issubset({1,2,3,4,6}):
        raise RuntimeError('one supported feature schema is required per corpus')
    torch.set_num_threads(4)
    torch.manual_seed(1701)
    device = torch.device(device_name if device_name != 'auto' else ('cuda' if torch.cuda.is_available() else 'cpu'))
    if device.type == 'cuda':
        device = torch.device('cuda', device.index if device.index is not None else 0)
        total = torch.cuda.get_device_properties(device).total_memory
        torch.cuda.set_per_process_memory_fraction(min(1, 1.5 * 1024**3 / total), device)
    class Network(nn.Module):
        def __init__(self, width):
            super().__init__(); self.width = width;self.schema=records[0].get('feature_schema',1)
            self.embedding = nn.Embedding(8192, width)
            nn.init.uniform_(self.embedding.weight, -.03, .03)
            self.bias = nn.Parameter(torch.zeros(width))
            self.output = nn.Parameter(torch.empty(width).uniform_(-.12, .12))
        def forward(self, indices, mask):
            sums = pooled_transform(indices,mask,self.embedding.weight,self.width,self.bias)
            values = sums.clamp(0, 1)
            return ((values[:, 0] - values[:, 1]) * self.output).sum(1)
    def tensor_batch(rows,feature_key='features'):
        import math
        indices=[];offsets=[0]
        target = []
        for row in rows:
            for p in range(2):
                ids = row[feature_key][p]
                indices.extend(ids);offsets.append(len(indices))
            search_target = math.tanh(row['search_cp'] / 600)
            if 'teacher_cp' in row:
                teacher_target=math.tanh(row['teacher_cp']/600)
                target.append(teacher_target if row['outcome'] is None else .9*teacher_target+.1*row['outcome'])
            else:target.append((row['outcome'] or 0) if row.get('expert') else search_target if row['outcome'] is None else .5 * search_target + .5 * row['outcome'])
        return torch.tensor(indices,dtype=torch.long,device=device),torch.tensor(offsets,dtype=torch.long,device=device),torch.tensor(target,device=device)
    train_rows = [r for r in records if r['game'] % 5 != 0]
    validation = [r for r in records if r['game'] % 5 == 0]
    if not train_rows or not validation:
        raise RuntimeError('need independent training and validation games')
    output.mkdir(parents=True, exist_ok=True)
    reports = []
    original_train=list(train_rows)
    for width in widths:
        train_rows=list(original_train)
        net = Network(width).to(device)
        optimizer = torch.optim.AdamW(net.parameters(), lr=.003)
        updates = 0
        best_loss=float('inf');best_state=None;best_epoch=0;best_optimizer=None
        rng = random.Random(1701)
        for epoch in range(epochs):
            resource_guard()
            rng.shuffle(train_rows)
            for start in range(0, len(train_rows), batch):
                x, mask, target = tensor_batch(train_rows[start:start + batch])
                optimizer.zero_grad(set_to_none=True)
                rows=train_rows[start:start+batch]
                supervised=torch.tensor([not row.get('expert') or row['outcome'] is not None or 'teacher_cp' in row for row in rows],device=device)
                errors=nn.functional.smooth_l1_loss(net(x, mask).tanh(), target,reduction='none')
                loss=(errors*supervised).sum()/supervised.sum().clamp_min(1)
                preferences=[row for row in rows if 'preferred_features' in row]
                if preferences:
                    px,pm,_=tensor_batch(preferences,'preferred_features');ax,am,_=tensor_batch(preferences,'alternative_features')
                    signs=torch.tensor([row['mover'] for row in preferences],device=device)
                    ranking=nn.functional.softplus(-signs*(net(px,pm)-net(ax,am))/.25).mean()
                    loss=loss+(.02 if 'teacher_cp' in rows[0] else .2)*ranking
                loss.backward(); optimizer.step(); updates += 1
            print(f'width={width} epoch={epoch + 1} loss={loss.item():.6f}', flush=True)
            with torch.no_grad():
                total=0.0;count=0
                for start in range(0,len(validation),batch):
                    rows=validation[start:start+batch];x,mask,target=tensor_batch(rows)
                    eligible=torch.tensor([not row.get('expert') or row['outcome'] is not None or 'teacher_cp' in row for row in rows],device=device)
                    errors=(net(x,mask).tanh()-target).square()
                    total+=(errors*eligible).sum().item();count+=eligible.sum().item()
                if not count:raise RuntimeError('no naturally finished validation games')
                if total/count<best_loss:
                    best_loss=total/count;best_epoch=epoch+1
                    best_state={key:value.detach().cpu().clone() for key,value in net.state_dict().items()}
                    best_optimizer=copy.deepcopy(optimizer.state_dict())
        net.load_state_dict(best_state)
        losses = []
        with torch.no_grad():
            for start in range(0, len(validation), batch):
                x, mask, target = tensor_batch(validation[start:start + batch])
                measured=[i for i,row in enumerate(validation[start:start+batch]) if not row.get('expert') or row['outcome'] is not None or 'teacher_cp' in row]
                losses.extend((net(x, mask).tanh() - target).square()[measured].cpu().tolist())
        if not losses:raise RuntimeError('no naturally finished validation games')
        path = output / f'nu-{width}.nnue'
        export(net, path)
        torch.save(dict(width=width, state=net.cpu().state_dict(), optimizer=best_optimizer,
                        epochs=epochs, selected_epoch=best_epoch, seed=1701), output / f'nu-{width}.pt')
        report = dict(width=width, updates=updates, validation_mse=sum(losses)/len(losses),
                      train_positions=len(train_rows), validation_positions=len(validation),
                      device=str(device), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                      peak_cuda_bytes=torch.cuda.max_memory_allocated() if device.type == 'cuda' else 0)
        report.update(corpus_sha256=hashlib.sha256(json.dumps(records,sort_keys=True).encode()).hexdigest(),
                      natural_games=len({r['game'] for r in records if r['outcome'] is not None}),
                      preference_positions=sum('preferred_features' in r for r in records),selected_epoch=best_epoch)
        reports.append(report)
        del optimizer, net, best_optimizer
        if device.type == 'cuda':
            torch.cuda.empty_cache()
    (output / 'training.json').write_text(json.dumps(reports, indent=2), encoding='utf8')

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, default=ROOT / 'build-nu/nu.exe')
    parser.add_argument('--data', type=Path, default=ROOT / 'Nu/work/bootstrap.jsonl')
    parser.add_argument('--output', type=Path, default=ROOT / 'Nu/work/models')
    parser.add_argument('--games', type=int, default=20)
    parser.add_argument('--cap', type=int, default=120)
    parser.add_argument('--milliseconds', type=float, default=10)
    parser.add_argument('--epochs', type=int, default=8)
    parser.add_argument('--batch', type=int, default=128)
    parser.add_argument('--device', default='auto')
    parser.add_argument('--source-model', type=Path)
    parser.add_argument('--widths',type=int,nargs='+',choices=(64,128),default=[64,128])
    args = parser.parse_args()
    if min(args.games, args.cap, args.epochs, args.batch) <= 0 or args.batch > 512:
        parser.error('positive limits required; batch <= 512')
    resource_guard()
    if args.data.exists() and args.data.stat().st_size > 256 * 1024**2:
        raise RuntimeError('corpus exceeds the bounded in-memory loader; shard before training')
    records = [json.loads(line) for line in args.data.read_text().splitlines()] if args.data.exists() else corpus(args.engine, args.data, args.games, args.cap, args.milliseconds, args.source_model)
    train(records, args.output, args.epochs, args.batch, args.device,tuple(args.widths))

if __name__ == '__main__':
    from research_job import run
    run(main)
