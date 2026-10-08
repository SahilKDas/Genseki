"""Pinned, per-ply resumable schema-7 collection; never count raw rows as accepted."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import random
import re
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from genseki.uhp import UhpProcess
from collect import active, storage_guard
from evidence import atomic_json, digest, REPETITION_POLICY
from gen1_teacher import Gen1Teacher
from learning import index_corpus
from position_keys import position_key
from research_job import check_deadline, run
from train import resource_guard, response


def white_target(target, mover):
    if target['orientation'] != 'side_to_move':
        raise RuntimeError('unknown teacher score orientation')
    if target['raw_score'] is None or abs(target['raw_score']) >= 30000:
        return None
    return target['raw_score'] * mover * 4


def snapshot(native):
    return dict(features=active(native), position=response(native, 'nu-position')[0],
                prior_white=int(response(native, 'nu-prior')[0]))


def legal_notation(native, move, legal):
    if move in legal:
        return move
    identity = response(native, 'nu-moveid ' + move)[0]
    for candidate in legal:
        if response(native, 'nu-moveid ' + candidate)[0] == identity:
            return candidate
    raise RuntimeError('teacher chose illegal parent move')


def accepted(directory, games):
    if not games:
        return 0, [0, 0]
    paths = [directory / f'game-{i:06d}.jsonl' for i in range(games)
             if (directory / f'game-{i:06d}.jsonl').stat().st_size]
    if not paths:
        return 0, [0, 0]
    samples=[];exposures={}
    for path in paths:
        with path.open(encoding='utf8') as handle:
            for line in handle:
                row=json.loads(line);family=position_key(row['opening_position'])
                split=int(hashlib.sha256(family.encode()).hexdigest()[:8],16)%5==0
                positions=[row['position']]+[child['position'] for child in row.get('observed_children',[])]
                keys={position_key(p) for p in positions}
                for key in keys:exposures[key]=exposures.get(key,0)|(2 if split else 1)
                samples.append((position_key(row['position']),int(split),keys))
    splits=[0,0];seen=set()
    for parent,split,keys in samples:
        if parent in seen or any(exposures[key]==3 for key in keys):continue
        seen.add(parent);splits[split]+=1
    return sum(splits),splits


def main():
    parser = argparse.ArgumentParser()
    for name in ('engine', 'teacher', 'referee', 'schema5', 'schema6', 'teacher-proof',
                 'exclusions', 'directory'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--positions', type=int, default=10000)
    parser.add_argument('--seed', type=int, default=300000)
    parser.add_argument('--stage', required=True)
    parser.add_argument('--wall-seconds', type=int, default=7200)
    args = parser.parse_args()
    if not 1 <= args.wall_seconds <= 7200 or not 1 <= args.positions <= 600000:
        parser.error('invalid bounded collection settings')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.stage):
        parser.error('stage must be a simple immutable name')
    resource_guard(); storage_guard(ROOT)
    proof = json.loads(args.teacher_proof.read_text())
    if not proof.get('passed') or proof['teacher_sha256'] != digest(args.teacher):
        raise RuntimeError('teacher lacks matching frozen Gen 1 verification')
    excluded = json.loads(args.exclusions.read_text())
    if excluded.get('key_version') != 'base-symmetry-opening-v2':
        raise RuntimeError('exclusion manifest must use current canonical keys')
    forbidden = set(excluded['positions']); forbidden_openings = set(excluded['opening_families'])
    config = dict(version=1, schema=7, seed=args.seed, positions=args.positions,
                  parent_depth=8, parent_ms=500, child_depth=8, child_ms=250,
                  cap=160, exploration=.08, repetition_policy=REPETITION_POLICY,
                  pins={name: digest(getattr(args, name.replace('-', '_')))
                        for name in ('engine', 'teacher', 'referee', 'schema5', 'schema6',
                                     'teacher-proof', 'exclusions')})
    args.directory.mkdir(parents=True, exist_ok=True)
    manifest = args.directory / 'manifest.json'
    state = json.loads(manifest.read_text()) if manifest.exists() else dict(config=config, games=0, accepted=0)
    if state['config'] != config:
        raise RuntimeError('immutable collection resume identity mismatch')
    while (args.directory / f"game-{state['games']:06d}.jsonl").exists():
        game_path = args.directory / f"game-{state['games']:06d}.jsonl"
        if not game_path.with_suffix('.replay.json').exists():
            raise RuntimeError('completed corpus lacks replay; preserve recovery evidence')
        state['games'] += 1
    if state['games']:
        state['accepted'], state['splits'] = accepted(args.directory, state['games'])
    atomic_json(manifest, state)
    stage_path = args.directory / ('stage-' + args.stage + '.json')
    stage = json.loads(stage_path.read_text()) if stage_path.exists() else dict(started=time.time(), limit=args.wall_seconds)
    if stage['limit'] != args.wall_seconds:
        raise RuntimeError('stage deadline identity mismatch')
    atomic_json(stage_path, stage)
    deadline = stage['started'] + stage['limit']
    if time.time() >= deadline:
        raise RuntimeError('stage already expired; its clock cannot be extended')
    peers = []
    with (args.directory / ('teacher-' + args.stage + '.log')).open('a+', encoding='utf8') as log:
        try:
            native = UhpProcess([str(args.engine.resolve()), '--feature-schema', '7']); peers.append(native)
            referee = UhpProcess([str(args.referee.resolve())]); peers.append(referee)
            teacher = Gen1Teacher(args.teacher, log); peers.append(teacher)
            actors = []
            for model in (args.schema5, args.schema6):
                actor = UhpProcess([str(args.engine.resolve()), '--model', str(model.resolve())]); peers.append(actor)
                for option in ('Threads 1', 'TableMiB 16', 'BackgroundPondering False',
                               'ThreatPlies 0', 'LateMoveReductions False'):
                    response(actor, 'options ' + option)
                actors.append(actor)
            if response(actors[0], 'nu-feature-schema') != ['5'] or response(actors[1], 'nu-feature-schema') != ['6']:
                raise RuntimeError('wrong incumbent model schema')
            progress_path = args.directory / 'progress.json'
            while state['accepted'] < args.positions and time.time() < deadline:
                check_deadline(); resource_guard(); storage_guard(ROOT)
                for name, expected in config['pins'].items():
                    if digest(getattr(args, name.replace('-', '_'))) != expected:
                        raise RuntimeError('collection artifact changed: ' + name)
                game = state['games']
                if progress_path.exists():
                    progress = json.loads(progress_path.read_text())
                    if progress['game'] == game - 1 and (args.directory / f"game-{progress['game']:06d}.jsonl").exists():
                        progress_path.unlink()
                        continue
                    if progress['game'] != game:
                        raise RuntimeError('collection progress/game mismatch')
                else:
                    for attempt in range(10000):
                        response(native, 'newgame Base'); rng = random.Random(args.seed + game + attempt*100000000)
                        opening_game = None
                        for _ in range(4):
                            opening_game = response(native, 'play ' + rng.choice(sorted(response(native, 'validmoves')[0].split(';'))))[0]
                        opening = snapshot(native)['position']
                        if position_key(opening) not in forbidden_openings:break
                    else:raise RuntimeError('no unreserved opening found')
                    progress = dict(game=game, ply=4, game_string=opening_game,
                                    opening_position=opening, opening_attempt=attempt, rows=[], rejected_rows=[], excluded=0)
                    atomic_json(progress_path, progress)
                if position_key(progress['opening_position']) in forbidden_openings:
                    raise RuntimeError('collection opening overlaps reserved family')
                response(native, 'newgame ' + progress['game_string'])
                outcome = None; termination = None
                resumed_result=progress['game_string'].split(';')[1]
                if resumed_result!='InProgress':
                    outcome={'WhiteWins':1,'BlackWins':-1,'Draw':0}[resumed_result];termination='natural'
                elif response(native,'nu-matchdraw')==['True']:termination='repetition'
                while not termination and progress['ply'] < 160 and time.time() < deadline-6:
                    check_deadline(); resource_guard()
                    ply = progress['ply']; rng = random.Random((args.seed + game) * 1000 + ply)
                    parent = snapshot(native); mover = 1 if parent['position'].split('|')[1] == 'w' else -1
                    target = teacher.search(progress['game_string'])
                    cp = white_target(target, mover)
                    row = dict(parent, feature_schema=7, strategic_prior_version=1,
                               game=game, seed=args.seed, source=config['pins']['teacher'], ply=ply,
                               game_string=progress['game_string'], opening_position=progress['opening_position'],
                               teacher=target, mover=mover, teacher_move=target['move'])
                    if cp is not None:
                        row['teacher_search_cp'] = cp
                    legal = sorted(response(native, 'validmoves')[0].split(';'))
                    preferred = legal_notation(native, target['move'], legal)
                    candidates = []; children = []
                    if ply % 4 == 0:
                        alternatives = [move for move in legal if move != preferred]
                        for move in [preferred] + rng.sample(alternatives, min(3, len(alternatives))):
                            child_game = response(native, 'play ' + move)[0]
                            child = dict(snapshot(native), move=move, game_string=child_game)
                            child['natural_result'] = child_game.split(';')[1]
                            children.append(child)
                            if child['natural_result'] == 'InProgress' and response(native, 'nu-matchdraw') == ['False']:
                                child_target = teacher.search(child_game, 8, 250)
                                child['teacher'] = child_target
                                child_cp = white_target(child_target, -mover)
                                if child_cp is not None:
                                    child['cp'] = child_cp; candidates.append(child)
                            response(native, 'undo')
                        if candidates:
                            row['alternatives'] = sorted(candidates, key=lambda c: c['cp'] * mover, reverse=True)
                    row['observed_children'] = children
                    exposures = [parent['position']] + [c['position'] for c in children]
                    if cp is not None and not any(position_key(p) in forbidden for p in exposures):
                        progress['rows'].append(row)
                    else:
                        progress['excluded'] += 1
                        progress['rejected_rows'].append(row)
                    move = preferred
                    if game % 4 >= 2 and ply % 2 == game % 2:
                        actor = actors[game % 4 - 2]
                        response(actor, 'newgame ' + progress['game_string'])
                        move = response(actor, 'bestmove depthorseconds 64 .230')[0]
                    if rng.random() < .08:
                        move = rng.choice(legal)
                    row['played_move'] = move
                    progress['game_string'] = response(native, 'play ' + move)[0]
                    position = response(referee, 'genseki-validate-game ' + progress['game_string'])[0]
                    if position != snapshot(native)['position']:
                        raise RuntimeError('collection rules-service board divergence')
                    progress['ply'] += 1
                    result = progress['game_string'].split(';')[1]
                    if result != 'InProgress':
                        outcome = {'WhiteWins': 1, 'BlackWins': -1, 'Draw': 0}[result]; termination = 'natural'
                    elif response(native, 'nu-matchdraw') == ['True']:
                        termination = 'repetition'
                    atomic_json(progress_path, progress)
                    if termination:
                        break
                if not termination and progress['ply'] < 160:
                    break
                termination = termination or 'ply_cap'
                for row in progress['rows']:
                    row.update(outcome=outcome, termination=termination)
                path = args.directory / f'game-{game:06d}.jsonl'
                if path.exists():
                    raise RuntimeError('completed game already exists; preserve recovery evidence')
                pending = path.with_suffix('.pending')
                with pending.open('w', encoding='utf8') as handle:
                    for row in progress['rows']:
                        handle.write(json.dumps(row, separators=(',', ':')) + '\n')
                    handle.flush(); os.fsync(handle.fileno())
                atomic_json(path.with_suffix('.replay.json'), dict(progress, outcome=outcome, termination=termination))
                os.replace(pending, path)
                state['games'] += 1
                state['accepted'], state['splits'] = accepted(args.directory, state['games'])
                state['completed'] = state['accepted'] >= args.positions
                atomic_json(manifest, state); progress_path.unlink()
                print(json.dumps({key: state[key] for key in ('games', 'accepted', 'splits', 'completed')}), flush=True)
            if state.get('completed'):
                paths=[p for p in sorted(args.directory.glob('game-*.jsonl')) if p.stat().st_size]
                db=index_corpus(paths,args.directory/'final-index.sqlite')
                final_splits=[db.execute('select count(*) from samples where split=?',(i,)).fetchone()[0] for i in (0,1)]
                db.close()
                if final_splits!=state['splits']:raise RuntimeError('accepted counting/index disagreement')
                atomic_json(args.directory/'inputs.json',[str(p.resolve()) for p in paths])
        except BaseException as error:
            atomic_json(args.directory / ('failure-' + args.stage + '.json'), dict(error=repr(error), state=state))
            raise
        finally:
            for peer in reversed(peers):
                peer.close()


if __name__ == '__main__':
    run(main)
