"""Lab-driven, full-width Gen 2 development. Never promotes an engine."""
import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time

import gen2 as g


def search(engine, depth, milliseconds):
    lines, elapsed = g.cmd(engine, f'alpha-search {depth} {milliseconds}', milliseconds / 1000 + 3)
    head = re.fullmatch(r'score (-?\d+) static (-?\d+) move (.+)', lines[0])
    stats = next((re.search(r'Explored (\d+) nodes to depth (\d+)', line) for line in lines
                  if 'Explored ' in line), None)
    if not head or not stats:
        raise RuntimeError('unrecognized search telemetry')
    return dict(score=int(head[1]), static=int(head[2]), move=head[3], nodes=int(stats[1]),
                depth=int(stats[2]), milliseconds=elapsed * 1000, pv=lines[1:])


def choose_and_regret(candidates, mover, field):
    if not candidates or mover not in (-1, 1):
        raise ValueError('invalid decision')
    if any(not math.isfinite(float(c[k])) for c in candidates for k in ('cp', field)):
        raise ValueError('nonfinite decision')
    chosen = max(range(len(candidates)), key=lambda i: candidates[i][field] * mover)
    best = max(c['cp'] * mover for c in candidates)
    return chosen, best - candidates[chosen]['cp'] * mover


def legal_positions(sources, stride):
    for path in sources:
        report = g.read(path)
        if report.get('config',{}).get('stage') != 'development':
            raise RuntimeError('only declared development arenas may supply lab data')
        if not report.get('valid', True):
            raise RuntimeError('invalid source arena')
        for game in report.get('games', []):
            moves = game['moves']
            identity = f'{g.digest(path)}:{game["index"]}'
            # Both colors from an opening belong to the same split.
            family = f'lab-development-opening-{game["opening_seed"]}'
            for ply in range(4, len(moves), stride):
                yield dict(id=f'{identity}:{ply}', source=identity, game=game['index'],
                           seed=game['opening_seed'], opening_family=family, ply=ply,
                           game_string='Base;;;' + ';'.join(moves[:ply]),
                           final_game='Base;;;' + ';'.join(moves),
                           source_termination=game['termination'],
                           student_loss=game.get('score') == 0,
                           mover=1 if ply % 2 == 0 else -1)


def slices(position, legal_ids, student_loss):
    occupied = {}
    for cell in position.split('|')[-1].split(';'):
        if cell:
            xy, stones = cell.split('=')
            occupied[tuple(map(int, xy.split(',')))] = stones.split(',')
    directions = ((1, 0), (0, 1), (-1, 1), (-1, 0), (0, -1), (1, -1))
    tags = []
    if any(len(stack) > 1 for stack in occupied.values()): tags.append('stacks')
    if any('Place(' in move for move in legal_ids): tags.append('reserve_deployment')
    for (q, r), stack in occupied.items():
        if any(stone in ('wQ', 'bQ') for stone in stack):
            if sum((q+dq, r+dr) in occupied for dq, dr in directions) >= 4:
                tags.append('queen_pressure')
    if student_loss: tags.append('student_loss_line')
    return sorted(set(tags)) or ['other']


def sources_for(args):
    return [Path(p).resolve() for p in args.sources]


def artifacts(args):
    return dict(binary=g.digest(g.ENGINE),model=g.digest(args.model),sidecar=g.digest(str(args.model)+'.alpha.json'))


def verify_artifacts(args,identity):
    if artifacts(args)!=identity:raise RuntimeError('lab artifacts changed during stage')


def replay(engine, game):
    current=g.cmd(engine,'newgame Base')[0][0]
    for move in game.split(';')[3:]:
        if move:current=g.cmd(engine,'play '+move)[0][0]
    return current


def collect(args, deadline):
    pinned=artifacts(args)
    root = g.WORK / args.corpus
    root.mkdir(parents=True, exist_ok=True)
    manifest_path = root / 'manifest.json'
    config = dict(kind='lab-full-width-v1', binary=g.digest(g.ENGINE), model=g.digest(args.model),
                  sidecar=g.digest(str(args.model)+'.alpha.json'),
                  sources={str(p): g.digest(p) for p in sources_for(args)}, stride=args.stride,
                  depth=args.depth, teacher_ms=args.teacher_ms, target=args.target,
                  openings='development only; no final qualification inputs')
    manifest = g.read(manifest_path) if manifest_path.exists() else dict(config=config, completed_ids=[], positions=0)
    if manifest['config'] != config: raise RuntimeError('decision corpus resume mismatch')
    files = sorted(root.glob('game-*.jsonl'))
    # A crash after row commit but before manifest commit is reconciled from rows.
    committed = {json.loads(p.read_text())['decision_id'] for p in files}
    with g.engine(g.ENGINE) as teacher, g.engine(g.ENGINE) as adapter, g.engine(g.ROOT/'build/genseki_rules.exe') as rules:
        g.settings(teacher); g.settings(adapter); g.neural(adapter, args.model)
        parents=sorted(legal_positions(sources_for(args), args.stride),key=lambda p:hashlib.sha256(p['id'].encode()).hexdigest())
        for parent in parents:
            if parent['id'] in committed: continue
            if len(committed) >= args.positions or time.monotonic() >= deadline: break
            verify_artifacts(args,pinned)
            if g.heavy_conflict():raise RuntimeError('competing heavy job; resumable stop')
            g.guard()
            final_state = replay(rules,parent['final_game']).split(';')[1]
            outcome = {'WhiteWins': 1, 'BlackWins': -1, 'Draw': 0}.get(final_state) if parent['source_termination']=='natural' else None
            parent_game=replay(rules,parent['game_string'])
            for e in (teacher, adapter): g.cmd(e, 'newgame '+parent_game)
            position = g.cmd(rules, 'genseki-position')[0][0]
            pf, _ = g.features(adapter, 'alpha-neural')
            legal = sorted(g.cmd(teacher, 'validmoves')[0][0].split(';'))
            move_ids = [g.cmd(adapter, 'alpha-moveid '+m)[0][0] for m in legal]
            children = []
            for move in legal:
                if time.monotonic()+args.teacher_ms/1000+0.1 >= deadline: break
                g.floors()
                results=[g.cmd(e, 'play '+move)[0][0] for e in (teacher, adapter, rules)]
                child_position = g.cmd(rules, 'genseki-position')[0][0]
                # Inspect the rules result independently of evaluator scores.
                child_game = results[2]
                terminal = {'WhiteWins': 1, 'BlackWins': -1, 'Draw': 0}.get(child_game.split(';')[1])
                repetition_draw = terminal is None and results[0].split(';')[1]=='Draw'
                cf, diagnostic = g.features(adapter, 'alpha-neural')
                raw_white = int(diagnostic[2].split()[1]) * -parent['mover']
                if repetition_draw:
                    cp=0;telemetry=None
                elif terminal is not None:
                    cp = terminal*6000; telemetry = None
                elif args.target == 'static':
                    cp = int(g.cmd(teacher, 'alpha-eval')[0][0].split()[1]) * -parent['mover'] * 4
                    telemetry = None
                else:
                    telemetry = search(teacher, args.depth, args.teacher_ms)
                    cp = max(-6000, min(6000, telemetry['score'] * -parent['mover'] * 4))
                children.append(dict(move=move, position=child_position, features=cf, cp=cp,
                                     prediction_white=0 if repetition_draw else terminal*6000 if terminal is not None else raw_white,
                                     terminal=terminal, repetition_draw=repetition_draw, telemetry=telemetry))
                for e in (teacher, adapter, rules): g.cmd(e, 'undo')
            if len(children) != len(legal): break  # Never retain a sampled decision.
            children.sort(key=lambda c: (-c['cp']*parent['mover'], c['move']))
            row = dict(parent, game_string=parent_game, decision_id=parent['id'], position=position, features=pf, feature_schema=4,
                       alternatives=children, legal_count=len(legal), full_width=True,
                       teacher_search_cp=children[0]['cp'], target_source=args.target,
                       outcome=outcome, termination='natural' if outcome is not None else parent['source_termination'],
                       slices=slices(position, move_ids, parent['student_loss']))
            path = root / f'game-{len(committed):06d}.jsonl'
            pending = path.with_suffix('.pending')
            with pending.open('w') as handle:
                handle.write(json.dumps(row, allow_nan=False)+'\n'); handle.flush(); os.fsync(handle.fileno())
            os.replace(pending, path); committed.add(parent['id'])
            manifest.update(completed_ids=sorted(committed), positions=len(committed), complete=len(committed)>=args.positions)
            g.atomic(manifest_path, manifest)
            print('full-width decisions', len(committed), 'children', len(children), flush=True)


def indexed(args):
    sys.path.insert(0, str(g.training_runtime())); import learning
    root = g.WORK / 'runs' / args.corpus; root.mkdir(parents=True, exist_ok=True)
    files = sorted((g.WORK/args.corpus).glob('game-*.jsonl'))
    if not files: raise RuntimeError('collect full-width decisions first')
    db, signature, excluded = g.curated_index(learning, files, root/'training-index.sqlite', root/'trained/nu-64-linear.resume.pt')
    return learning, root, db, signature, excluded


def audit(args, deadline):
    pinned=artifacts(args)
    _, _, db, signature, _ = indexed(args)
    report = dict(binary_sha256=g.digest(g.ENGINE), model_sha256=g.digest(args.model),
                  split='held-out opening families', tactical_exclusions=signature, decisions=[])
    try:
        with g.engine(g.ENGINE) as adapter:
            g.settings(adapter); g.neural(adapter, args.model)
            for (payload,) in db.execute('select payload from samples where split=1 order by id'):
                verify_artifacts(args,pinned)
                row = json.loads(payload)
                if not row.get('full_width'): raise RuntimeError('sampled decisions are not a full-width audit')
                candidates = []
                for child in row['alternatives']:
                    if time.monotonic() >= deadline: raise RuntimeError('audit stage expired; no complete claim')
                    g.cmd(adapter, 'newgame '+row['game_string']); g.cmd(adapter, 'play '+child['move'])
                    _, diagnostic = g.features(adapter, 'alpha-neural')
                    value = int(diagnostic[2].split()[1]) * -row['mover']
                    candidates.append(dict(child, prediction_white=0 if child.get('repetition_draw') else child['terminal']*6000 if child['terminal'] is not None else value))
                chosen, regret = choose_and_regret(candidates, row['mover'], 'prediction_white')
                report['decisions'].append(dict(id=row['decision_id'], chosen=candidates[chosen]['move'],
                                                regret_gen1_units=regret/4, agreement=regret==0, slices=row['slices']))
        if not report['decisions']: raise RuntimeError('no held-out decisions; collect more opening families')
        report['mean_regret_gen1_units'] = sum(d['regret_gen1_units'] for d in report['decisions'])/len(report['decisions'])
        report['top_choice_agreement'] = sum(d['agreement'] for d in report['decisions'])/len(report['decisions'])
        report['slice_counts'] = dict(collections.Counter(tag for d in report['decisions'] for tag in d['slices']))
        report['complete'] = True
        g.atomic(g.REPORT/(args.name+'-decision-audit.json'), report)
        print(report['mean_regret_gen1_units'], report['top_choice_agreement'])
    finally: db.close()


def compare(args, deadline):
    pinned=artifacts(args)
    report = dict(binary_sha256=g.digest(g.ENGINE), model_sha256=g.digest(args.model), records=[])
    parents=sorted(legal_positions(sources_for(args), args.stride),key=lambda p:hashlib.sha256(p['id'].encode()).hexdigest())
    for parent in parents[:args.positions]:
        for kind, depth, ms in (('fixed_depth', args.depth, 2000), ('fixed_time', 8, 230)):
            paired = {}
            for mode in ('gen1', 'neural'):
                verify_artifacts(args,pinned)
                if time.monotonic()+ms/1000+0.1 >= deadline: raise RuntimeError('comparison deadline; no complete claim')
                g.floors()
                with g.engine(g.ENGINE) as e:
                    g.settings(e, args.threads)
                    if mode == 'neural': g.neural(e, args.model)
                    g.cmd(e, 'newgame '+parent['game_string'])
                    diagnostic = g.features(e, 'alpha-neural')[1] if mode=='neural' else []
                    paired[mode] = search(e, depth, ms) | dict(evaluator=mode, diagnostics=diagnostic)
                    if mode=='neural':paired[mode]['feature_cache']=g.cmd(e,'alpha-feature-cache')[0]
            report['records'].append(dict(position=parent['id'], kind=kind, searches=paired,
                                         equal_completed_depth=all(s['depth']==depth for s in paired.values()) if kind=='fixed_depth' else None))
    report.update(complete=True, production_promoted=False, time_mode='fresh serial diagnostic searches; not a gauntlet')
    g.atomic(g.REPORT/(args.name+'-paired-search.json'), report)
    print('paired positions', len(report['records']))


def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode', choices=('collect','audit','compare'))
    p.add_argument('--model', type=Path, required=True)
    p.add_argument('--sources', nargs='+', required=True)
    p.add_argument('--corpus', default='lab-v1'); p.add_argument('--name', default='lab-v1')
    p.add_argument('--stage-id', required=True); p.add_argument('--seconds', type=int, default=600)
    p.add_argument('--positions', type=int, default=32); p.add_argument('--stride', type=int, default=8)
    p.add_argument('--depth', type=int, default=3); p.add_argument('--teacher-ms', type=int, default=250)
    p.add_argument('--threads', type=int, default=1); p.add_argument('--target', choices=('static','search'), default='search')
    args=p.parse_args()
    g.WORK.mkdir(parents=True,exist_ok=True)
    for value in (args.corpus,args.name,args.stage_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]+',value) or value.lower()=='iota': p.error('safe namespace required')
    for path in [args.model,*sources_for(args)]:
        if 'iota' in [s.lower() for s in path.resolve().parts]: p.error('Iota is excluded')
    if not (1<=args.seconds<=7200 and 1<=args.positions<=10000 and 1<=args.stride<=160 and 1<=args.depth<=8 and 1<=args.teacher_ms<=2000 and 1<=args.threads<=12): p.error('bounded stage settings required')
    if args.threads!=1: p.error('paired diagnostic search is serial; use one thread for all modes')
    lock=(g.WORK/'stage.lock').open('a+b'); lock.write(b'0'); lock.flush(); lock.seek(0)
    try:
        if os.name=='nt':
            import ctypes,msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
            ctypes.windll.kernel32.SetPriorityClass(ctypes.windll.kernel32.GetCurrentProcess(),0x40)
        if g.heavy_conflict(): raise RuntimeError('conflicting heavy campaign')
        g.guard(); g.freeze_search()
        config=vars(args)|dict(model=str(args.model.resolve()),sources={str(p):g.digest(p) for p in sources_for(args)},binary=g.digest(g.ENGINE),model_sha256=g.digest(args.model),sidecar_sha256=g.digest(str(args.model)+'.alpha.json'))
        config.pop('seconds'); path=g.REPORT/'stages'/(args.stage_id+'.json')
        progress,remaining=g.stage_start(path,config,args.seconds)
        try:
            {'collect':collect,'audit':audit,'compare':compare}[args.mode](args,time.monotonic()+remaining)
            progress.update(status='returned',finished=time.time())
        except Exception as error:
            progress.setdefault('failures',[]).append(dict(time=time.time(),error=repr(error)))
            progress.update(status='failed',error=repr(error)); raise
        finally: g.atomic(path,progress)
    finally: lock.close()


if __name__=='__main__': main()
