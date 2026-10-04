from __future__ import annotations

import ctypes
import gzip
import hashlib
import io
import json
import math
import os
import queue
import random
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import torch
from torch import nn

from genseki.nokamute_gate import UhpProcess
from genseki.training import piece_slot


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp')
    with tmp.open('wb') as f:
        f.write(data)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_json(path, value):
    atomic(path, json.dumps(value, indent=2, allow_nan=False).encode())


def encode(position):
    """All 22 pieces, unbounded translated coordinates; no heuristic labels/features."""
    fields = position.split('|')
    if len(fields) != 6 or fields[0] != 'G1':
        raise ValueError('invalid native position')
    stacks = []
    for cell in fields[5].split(';') if fields[5] else []:
        coords, pieces = cell.split('=')
        q, r = map(int, coords.split(','))
        stacks.append((q, r, pieces.split(',')))
    cq = sum(s[0] for s in stacks) / max(1, len(stacks))
    cr = sum(s[1] for s in stacks) / max(1, len(stacks))
    x = np.zeros(136, dtype=np.float32)
    for q, r, pieces in stacks:
        for height, token in enumerate(pieces):
            i = piece_slot(token) * 6
            x[i:i+6] = [1, (q-cq)/12, (r-cr)/12, height/4,
                        float(height == len(pieces)-1), len(pieces)/4]
    x[132:] = [1 if fields[1] == 'w' else -1, int(fields[2])/160,
                int(fields[3])/80, int(fields[4])/80]
    return x


class Network(nn.Module):
    """Shared state embedding and variable legal-successor scorer (150,274 parameters)."""
    def __init__(self):
        super().__init__()
        self.trunk = nn.Sequential(nn.Linear(136, 256), nn.ReLU(),
                                   nn.Linear(256, 256), nn.ReLU())
        self.value = nn.Sequential(nn.Linear(256, 64), nn.ReLU(), nn.Linear(64, 1), nn.Tanh())
        self.policy = nn.Sequential(nn.Linear(512, 64), nn.ReLU(), nn.Linear(64, 1))

    def forward(self, states, children, owners):
        h = self.trunk(states)
        c = self.trunk(children)
        logits = self.policy(torch.cat([h[owners], c], dim=1)).squeeze(-1)
        return logits, self.value(h).squeeze(-1)

    def evaluate_value(self, positions):
        """Player-to-move value; shared interface for a future native PVS adapter."""
        device = next(self.parameters()).device
        with torch.inference_mode():
            return self.value(self.trunk(torch.as_tensor(np.stack([encode(p) for p in positions]),
                                                        device=device))).squeeze(-1).cpu().tolist()


def save_model(path, model, metadata):
    stream = io.BytesIO()
    torch.save({'state_dict': model.cpu().state_dict(), 'metadata': metadata}, stream)
    candidate = Path(path).with_name(Path(path).name + '.verify')
    atomic(candidate, stream.getvalue())
    load_model(candidate)
    os.replace(candidate, path)
    return digest(path)


def load_model(path):
    artifact = torch.load(path, map_location='cpu', weights_only=True)
    model = Network()
    model.load_state_dict(artifact['state_dict'])
    if not all(torch.isfinite(p).all() for p in model.parameters()):
        raise ValueError('nonfinite model')
    return model.eval(), artifact['metadata']


class StopWork(Exception):
    pass


def available_ram():
    if os.name == 'nt':
        class Memory(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in
                ('total', 'available', 'page_total', 'page_available', 'virtual', 'virtual_available', 'extended')]
        m = Memory()
        m.length = ctypes.sizeof(m)
        if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m)):
            raise OSError('RAM watchdog unavailable')
        return m.available
    return os.sysconf('SC_AVPHYS_PAGES') * os.sysconf('SC_PAGE_SIZE')


def folder_bytes(root):
    return sum(p.stat().st_size for p in Path(root).rglob('*') if p.is_file())


class Guard:
    def __init__(self, root, deadline, disk_cap=2_000_000_000):
        self.root, self.deadline, self.disk_cap = Path(root), deadline, disk_cap
        self.metrics = {'peak_disk_bytes': 0, 'minimum_available_ram_bytes': None,
                        'peak_gpu_allocated_bytes': 0, 'peak_gpu_reserved_bytes': 0,
                        'peak_process_ram_bytes': 0, 'peak_native_process_count': 0}
        self.last_disk = 0
        self.process_count = 0
        self.process_lock = threading.Lock()

    def check(self):
        if time.monotonic() >= self.deadline:
            raise StopWork('hard deadline')
        free = available_ram()
        if os.name == 'nt':
            class Counters(ctypes.Structure):
                _fields_ = [('cb', ctypes.c_ulong), ('faults', ctypes.c_ulong)] + [
                    (name, ctypes.c_size_t) for name in ('peak', 'working', 'quota_peak_paged',
                     'quota_paged', 'quota_peak_nonpaged', 'quota_nonpaged', 'pagefile', 'peak_pagefile')]
            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            get_handle = ctypes.windll.kernel32.GetCurrentProcess
            get_handle.restype = ctypes.c_void_p
            get_info = ctypes.windll.psapi.GetProcessMemoryInfo
            # The structure type is local; a class-specific global ctypes signature
            # races across workers. The API accepts a pointer to the same fixed layout.
            get_info.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
            if get_info(get_handle(), ctypes.byref(counters), counters.cb):
                self.metrics['peak_process_ram_bytes'] = max(self.metrics['peak_process_ram_bytes'], counters.peak)
        old = self.metrics['minimum_available_ram_bytes']
        self.metrics['minimum_available_ram_bytes'] = min(old or free, free)
        if free < 1024**3:
            raise StopWork('emergency RAM floor')
        if free < 2*1024**3:
            raise StopWork('RAM below 2 GiB; resume when memory is available')
        if time.monotonic() - self.last_disk > 2:
            used = folder_bytes(self.root)
            self.metrics['peak_disk_bytes'] = max(self.metrics['peak_disk_bytes'], used)
            self.last_disk = time.monotonic()
            # Reserve headroom for atomic writes and reports; stop before the cap.
            if used > self.disk_cap - 16_000_000 or shutil.disk_usage(self.root).free < 512_000_000:
                raise StopWork('disk headroom exhausted')
        if torch.cuda.is_initialized():
            allocated, reserved = torch.cuda.max_memory_allocated(), torch.cuda.max_memory_reserved()
            self.metrics['peak_gpu_allocated_bytes'] = max(self.metrics['peak_gpu_allocated_bytes'], allocated)
            self.metrics['peak_gpu_reserved_bytes'] = max(self.metrics['peak_gpu_reserved_bytes'], reserved)
            if allocated > int(1.5*1024**3):
                raise StopWork('VRAM ceiling')


class RulesProcess(UhpProcess):
    def __init__(self, command, guard):
        self.guard = guard
        try:
            super().__init__(command)
        except BaseException:
            if hasattr(self, 'process'):
                self.kill()
                if hasattr(self, 'reader'):
                    self.reader.join(timeout=.2)
                for pipe in (self.process.stdin, self.process.stdout):
                    if pipe is not None:
                        pipe.close()
            raise

    def read_response(self, timeout):
        self.guard.check()
        return super().read_response(min(timeout, max(.001, self.guard.deadline-time.monotonic())))


class Board:
    """One bounded-response native rules subprocess per worker, always closed by its owner."""
    def __init__(self, executable, guard):
        self.guard = guard
        self.native = RulesProcess([str(Path(executable).resolve())], guard)
        with guard.process_lock:
            guard.process_count += 1
            guard.metrics['peak_native_process_count'] = max(guard.metrics['peak_native_process_count'], guard.process_count)
        try:
            self.game = self.command('newgame')[0]
        except BaseException:
            self.close()
            raise

    def command(self, text):
        self.guard.check()
        remaining = min(self.guard.deadline, getattr(self, 'operation_deadline', self.guard.deadline)) - time.monotonic()
        if remaining <= 0:
            raise StopWork('move search deadline')
        response, _ = self.native.command(text, timeout=max(.001, min(5, remaining)))
        if any(line.startswith(('err ', 'invalidmove ')) for line in response):
            raise ValueError(response)
        return response[:-1]

    @property
    def side(self):
        return 'w' if self.game.split(';')[2].startswith('White') else 'b'

    def terminal(self):
        result = self.game.split(';')[1]
        if result in ('NotStarted', 'InProgress'):
            return None
        winner = {'WhiteWins': 'w', 'BlackWins': 'b', 'Draw': None}[result]
        return 0. if winner is None else (1. if winner == self.side else -1.)

    def position(self):
        return self.command('genseki-position')[0]

    def children(self):
        return [line.split('\t', 1) for line in self.command('genseki-children')]

    def play(self, move):
        self.game = self.command('pass' if move == 'pass' else 'play ' + move)[0]

    def undo(self):
        self.game = self.command('undo')[0]

    def close(self):
        # Immediate kill at expiration avoids a protocol shutdown extending the deadline.
        if time.monotonic() >= self.guard.deadline:
            self.native.kill()
        else:
            self.native.close()
        self.native.reader.join(timeout=.2)
        for pipe in (self.native.process.stdin, self.native.process.stdout):
            if pipe is not None:
                pipe.close()
        with self.guard.process_lock:
            self.guard.process_count -= 1


@dataclass
class Node:
    prior: float = 1.
    visits: int = 0
    total: float = 0.
    children: dict = field(default_factory=dict)


def search(board, model, rng, simulations=64, cpuct=1.5, noise=False):
    root = Node()

    def expand(node):
        outcome = board.terminal()
        if outcome is not None:
            return outcome
        legal = board.children()
        if not legal:
            raise ValueError('nonterminal node has no legal moves')
        state = torch.from_numpy(encode(board.position())).unsqueeze(0)
        children = torch.from_numpy(np.stack([encode(p) for _, p in legal]))
        with torch.inference_mode():
            logits, value = model(state, children, torch.zeros(len(legal), dtype=torch.long))
            priors = logits.softmax(0).numpy()
        node.children = {m: Node(float(p)) for (m, _), p in zip(legal, priors)}
        return float(value.item())

    if board.terminal() is not None:
        return [], [], []
    expand(root)
    if noise:
        samples = rng.dirichlet(np.full(len(root.children), .3))
        for child, sample in zip(root.children.values(), samples):
            child.prior = .75*child.prior + .25*float(sample)
    for _ in range(simulations):
        board.guard.check()
        node, path, depth = root, [root], 0
        try:
            while node.children:
                move, child = max(node.children.items(), key=lambda item:
                    -item[1].total/max(1, item[1].visits) +
                    cpuct*item[1].prior*math.sqrt(node.visits+1)/(1+item[1].visits))
                board.play(move)
                depth += 1
                node = child
                path.append(node)
            value = expand(node)
            # Node values are from that node's player-to-move perspective.
            for ancestor in reversed(path):
                ancestor.visits += 1
                ancestor.total += value
                value = -value
        finally:
            for _ in range(depth):
                board.undo()
    return list(root.children), [c.visits for c in root.children.values()], board.children()


def play_game(executable, models, config, seed, guard, exploration=True, opening=None):
    rng = np.random.default_rng(seed)
    board = Board(executable, guard)
    examples, moves, move_times = [], [], []
    started = time.monotonic()
    try:
        for move in opening or []:
            board.play(move)
            moves.append(move)
        for ply in range(len(moves), config['max_plies']):
            if board.terminal() is not None:
                break
            side, position, game = board.side, board.position(), board.game
            move_started = time.monotonic()
            board.operation_deadline = min(guard.deadline, move_started+config.get('move_seconds', 30.))
            legal, visits, children = search(board, models[side], rng, config['simulations'],
                                             config['cpuct'], exploration)
            board.operation_deadline = guard.deadline
            move_times.append(time.monotonic()-move_started)
            counts = np.asarray(visits, dtype=np.float64)
            policy = counts/counts.sum()
            if exploration:
                # Continue neural search throughout the game; lower, nonzero late temperature.
                temperature = 1. if ply < 24 else .5
                selection = counts**(1/temperature)
                selection /= selection.sum()
                index = int(rng.choice(len(legal), p=selection))
            else:
                index = int(np.argmax(counts))
            examples.append({'position': position, 'game': game, 'moves': legal,
                             'visits': visits, 'side': side})
            board.play(legal[index])
            moves.append(legal[index])
        result = board.terminal()
        winner = None if result is None or result == 0 else (board.side if result == 1 else
                                                           ('b' if board.side == 'w' else 'w'))
        for example in examples:
            example['z'] = None if result is None else (0 if winner is None else
                            (1 if winner == example['side'] else -1))
        return examples, {'seed': seed, 'moves': moves, 'final_game': board.game,
                          'natural': result is not None, 'reason': 'terminal' if result is not None else 'ply_cap',
                          'winner': winner, 'elapsed_seconds': time.monotonic()-started,
                          'move_seconds': move_times, 'maximum_move_seconds': max(move_times, default=0)}
    finally:
        board.close()


class Replay:
    """One compressed game per shard; FIFO eviction. Manifest hashes detect corruption."""
    def __init__(self, root, capacity):
        self.root, self.capacity = Path(root), capacity
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / 'index.json'
        self.items = json.loads(self.manifest.read_text()) if self.manifest.exists() else []
        if not self.manifest.exists():
            write_json(self.manifest, self.items)
        known = {i['file'] for i in self.items}
        for p in self.root.glob('*.gz'):
            if p.name not in known:
                p.unlink()  # Uncommitted shard from interrupted transaction.
        for item in self.items:
            if digest(self.root/item['file']) != item['sha256']:
                raise ValueError('replay corruption: ' + item['file'])

    @property
    def size(self):
        return sum(i['positions'] for i in self.items)

    def add(self, examples, metadata):
        if not examples:
            return
        examples = examples[-self.capacity:]
        name = f"game-{time.time_ns()}.json.gz"
        atomic(self.root/name, gzip.compress(json.dumps({'examples': examples, 'metadata': metadata}).encode()))
        self.items.append({'file': name, 'positions': len(examples), 'sha256': digest(self.root/name)})
        removed = []
        while self.size > self.capacity:
            removed.append(self.items.pop(0))
        write_json(self.manifest, self.items)
        for item in removed:
            (self.root/item['file']).unlink(missing_ok=True)

    def sample(self, count, seed):
        # Reservoir sampling avoids loading the entire 200k-position replay into RAM.
        rng, reservoir, seen = random.Random(seed), [], 0
        for item in self.items:
            data = json.loads(gzip.decompress((self.root/item['file']).read_bytes()))
            for example in data['examples']:
                seen += 1
                if len(reservoir) < count:
                    reservoir.append(example)
                else:
                    index = rng.randrange(seen)
                    if index < count:
                        reservoir[index] = example
        return reservoir


def train(model, examples, executable, config, guard, seed):
    torch.manual_seed(seed)
    rng = random.Random(seed)
    # Split by entire game, avoiding adjacent-position validation leakage.
    game_ids = sorted({e['game_id'] for e in examples})
    rng.shuffle(game_ids)
    labeled_ids = {e['game_id'] for e in examples if e['z'] is not None}
    natural_ids = [g for g in game_ids if g in labeled_ids]
    capped_ids = [g for g in game_ids if g not in labeled_ids]
    # Keep at least one terminal game in training. With only one terminal game,
    # value validation is unavailable, instead of withholding all value labels.
    validation_ids = set(natural_ids[:max(1, len(natural_ids)//5)]) if len(natural_ids) > 1 else set()
    if len(capped_ids) > 1 or (capped_ids and natural_ids):
        validation_ids.update(capped_ids[:max(1, len(capped_ids)//5)])
    training = [e for e in examples if e['game_id'] not in validation_ids]
    validation = [e for e in examples if e['game_id'] in validation_ids]
    if not training:
        raise ValueError('empty training split')
    device = config['device']
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device == 'cuda':
        if not torch.cuda.is_available():
            raise ValueError('CUDA requested but unavailable')
        torch.cuda.set_per_process_memory_fraction(min(1., 1.5*1024**3/torch.cuda.get_device_properties(0).total_memory))
    model.to(device).train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=config['learning_rate'])
    board = Board(executable, guard)
    history = []
    batch_size = config['batch_size']

    def loss_batch(batch):
        states, children, owners, targets, sizes = [], [], [], [], []
        for index, e in enumerate(batch):
            board.game = board.command('newgame ' + e['game'])[0]
            legal = board.children()
            if [m for m, _ in legal] != e['moves']:
                raise ValueError('replay legal moves changed')
            states.append(encode(e['position']))
            children.extend(encode(p) for _, p in legal)
            owners.extend([index]*len(legal))
            visits = np.asarray(e['visits'], dtype=np.float32)
            targets.append(torch.as_tensor(visits/visits.sum(), device=device))
            sizes.append(len(legal))
        logits, values = model(torch.as_tensor(np.stack(states), device=device),
                               torch.as_tensor(np.stack(children), device=device),
                               torch.tensor(owners, device=device))
        policy = torch.stack([-(t*l.log_softmax(0)).sum() for t, l in
                              zip(targets, logits.split(sizes))]).mean()
        mask = torch.tensor([e['z'] is not None for e in batch], device=device)
        value = ((values[mask]-torch.tensor([e['z'] for e in batch if e['z'] is not None],
                                           device=device))**2).mean() if mask.any() else values.sum()*0
        return policy, value

    try:
        for epoch in range(config['epochs']):
            rng.shuffle(training)
            sums, updates, offset = [0., 0.], 0, 0
            while offset < len(training):
                guard.check()
                try:
                    optimizer.zero_grad(set_to_none=True)
                    p, v = loss_batch(training[offset:offset+batch_size])
                    (p+v).backward()
                    nn.utils.clip_grad_norm_(model.parameters(), 1.)
                    guard.check()
                    optimizer.step()
                    sums[0] += p.item()
                    sums[1] += v.item()
                    updates += 1
                    offset += batch_size
                except torch.cuda.OutOfMemoryError:
                    optimizer.zero_grad(set_to_none=True)
                    p = v = None
                    if batch_size == 1:
                        raise
                    batch_size = max(1, batch_size//2)
                    torch.cuda.empty_cache()
            model.eval()
            val = []
            with torch.no_grad():
                for offset in range(0, len(validation), batch_size):
                    p, v = loss_batch(validation[offset:offset+batch_size])
                    val.append([p.item(), v.item()])
            history.append({'epoch': epoch, 'policy_loss': sums[0]/updates,
                            'value_loss': sums[1]/updates, 'optimizer_updates': updates,
                            'validation': np.mean(val, axis=0).tolist() if val else None})
            model.train()
        return {'history': history, 'training_positions': len(training),
                'validation_positions': len(validation), 'effective_batch_size': batch_size,
                'value_labeled_positions': sum(e['z'] is not None for e in examples),
                'training_value_positions': sum(e['z'] is not None for e in training),
                'validation_value_positions': sum(e['z'] is not None for e in validation),
                'device': device}
    finally:
        model.cpu().eval()
        board.close()


def arena(executable, champion, challenger, config, seed, guard):
    records = []
    for pair in range(config['arena_games']//2):
        rng = np.random.default_rng(seed+pair)
        board = Board(executable, guard)
        opening = []
        try:
            for _ in range(4):
                legal = board.children()
                move = legal[int(rng.integers(len(legal)))][0]
                opening.append(move)
                board.play(move)
        finally:
            board.close()
        for color in ('w', 'b'):
            models = {'w': champion, 'b': champion}
            models[color] = challenger
            _, record = play_game(executable, models, config, seed+pair, guard, False, opening)
            record.update(challenger_color=color, opening_seed=seed+pair, opening=opening)
            record['score'] = .5 if record['winner'] is None else float(record['winner'] == color)
            records.append(record)
    score = sum(r['score'] for r in records)/len(records)
    wins = sum(r['score'] == 1 for r in records)
    losses = sum(r['score'] == 0 for r in records)
    return {'games': records, 'wins': wins, 'losses': losses, 'draws': len(records)-wins-losses,
            'score': score, 'complete': len(records) == config['arena_games'],
            'promotion_heuristic': 'development only; no statistical strength claim'}


def promote(root, state, candidate, report, threshold):
    if not report.get('complete') or report['score'] < threshold:
        return False
    model, metadata = load_model(candidate)
    generation = metadata['generation']
    immutable = Path(root)/'checkpoints'/f'G{generation}.pt'
    if immutable.exists():
        raise ValueError('lineage checkpoint already exists')
    atomic(immutable, Path(candidate).read_bytes())
    entry = {'generation': generation, 'sha256': digest(immutable),
             'checkpoint': str(immutable.relative_to(root)), 'arena_score': report['score']}
    # State is the authoritative commit point. Recovery restores canonical bytes from it.
    new_state = dict(state)
    new_state['champion'] = entry
    new_state['lineage'] = state['lineage'] + [entry]
    write_json(Path(root)/'state.json', new_state)
    state.update(new_state)
    atomic(Path(root)/'champion'/'rho.pt', immutable.read_bytes())
    return True


def recover(root):
    root = Path(root)
    path = root/'state.json'
    try:
        state = json.loads(path.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        backup = root/'state.backup.json'
        if not backup.exists():
            raise
        state = json.loads(backup.read_text())
    entry = state['champion']
    source = root/entry['checkpoint']
    if digest(source) != entry['sha256']:
        raise ValueError('authoritative champion corrupt; refusing fallback')
    load_model(source)
    champion = root/'champion'/'rho.pt'
    if not champion.exists() or digest(champion) != entry['sha256']:
        atomic(champion, source.read_bytes())
    for pattern in ('*.tmp', '*.verify'):
        for p in root.rglob(pattern):
            p.unlink()
    write_json(path, state)
    return state
