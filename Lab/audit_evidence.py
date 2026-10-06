"""Read frozen evidence; write only within Lab. No engine or training processes."""
import collections
import hashlib
import json
import math
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parent.parent
LAB = Path(__file__).resolve().parent

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def retain(path):
    raw = path.read_bytes()
    target = LAB / 'snapshot' / path.relative_to(ROOT)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()

def distribution(values):
    if not values:
        return {}
    ordered = sorted(values)
    return dict(n=len(values), minimum=ordered[0], median=statistics.median(values),
                mean=statistics.mean(values), p90=ordered[int(.9*(len(ordered)-1))], maximum=ordered[-1])

def main():
    base = ROOT / 'Nu/work/campaign-v6'
    result = {'scope': 'Existing frozen evidence only; no new strength test', 'inputs': {}}
    training = base / 'models/training.json'
    result['training'] = json.loads(training.read_text())
    result['inputs'][str(training.relative_to(ROOT))] = retain(training)
    arenas = []
    for path in sorted(base.glob('*-development.json')):
        value = json.loads(path.read_text())
        games = value.get('games', [])
        depths, nodes, scores = [], [], []
        late_loss_scores = []
        for game in games:
            for search in game.get('searches', []):
                for text in search.get('info', []):
                    found = re.search(r'depth (\d+) nodes (\d+) score (-?\d+)', text)
                    if found:
                        d, n, s = map(int, found.groups())
                        depths.append(d); nodes.append(n); scores.append(s)
                        if game.get('score') == 0 and game.get('termination') == 'natural' and search.get('ply', 0) >= len(game.get('moves', []))-6 and abs(s)<90000:
                            late_loss_scores.append(s)
        arenas.append(dict(file=str(path.relative_to(ROOT)), games=len(games),
                           points=sum(g.get('score', 0) for g in games),
                           terminations=dict(collections.Counter(g.get('termination') for g in games)),
                           results=dict(collections.Counter(g.get('result') for g in games)),
                           completed_depth=distribution(depths), nodes=distribution(nodes),
                           score=distribution(scores), late_loss_nonterminal_score=distribution(late_loss_scores),
                           late_loss_positive=sum(s>0 for s in late_loss_scores)))
        result['inputs'][str(path.relative_to(ROOT))] = retain(path)
    result['arenas'] = arenas
    timing = base / 'final-thread-timing.json'
    groups = collections.defaultdict(list)
    for row in json.loads(timing.read_text()).get('measurements', []):
        groups[row['threads']].append(row)
    result['profile'] = {}
    for thread, rows in groups.items():
        times = sum(row['milliseconds'] for row in rows) * 1e6
        feature = sum(row.get('profile', {}).get('features_ns', 0) for row in rows)
        result['profile'][thread] = dict(samples=len(rows),
            wall_ms=distribution([row['milliseconds'] for row in rows]),
            depth=distribution([row['depth'] for row in rows]),
            nodes=distribution([row['nodes'] for row in rows]),
            feature_ns_sum=feature, wall_ns_sum=times,
            feature_worker_time_over_wall=feature/times if times else None)
    result['inputs'][str(timing.relative_to(ROOT))] = retain(timing)
    cp, static, pv, ply = [], [], [], []
    terminal = collections.Counter()
    feature_duplicates, feature_total = 0, 0
    sign_disagree = 0
    corpus_hash = hashlib.sha256()
    for path in sorted((base / 'corpus').glob('game-*.jsonl')):
        raw = path.read_bytes(); corpus_hash.update(path.name.encode()); corpus_hash.update(raw)
        rows = [json.loads(line) for line in raw.splitlines() if line]
        if rows: terminal[rows[0].get('termination')] += 1
        for row in rows:
            s = row.get('teacher_search_cp', 0); t = row.get('teacher_cp', 0)
            cp.append(s); static.append(t); pv.append(row.get('teacher_pv_length', 0)); ply.append(row['ply'])
            sign_disagree += s*t < 0
            for features in row.get('features', []):
                feature_total += len(features); feature_duplicates += len(features)-len(set(features))
    result['corpus'] = dict(positions=len(cp), games_by_termination=dict(terminal),
        search_score=distribution(cp), static_score=distribution(static),
        search_pv_length=distribution(pv), ply=distribution(ply),
        static_search_opposite_sign=sign_disagree,
        abs_search_over_1200=sum(abs(x)>1200 for x in cp),
        abs_search_over_2400=sum(abs(x)>2400 for x in cp),
        active_feature_count=feature_total, repeated_active_indices=feature_duplicates,
        ordered_file_content_sha256=corpus_hash.hexdigest())
    source_paths = ['.tmp/nu-nokamute/src/eval.rs', '.tmp/nu-nokamute/src/player.rs',
                    'Nu/src/features.hpp', 'Nu/src/model.hpp', 'Nu/src/state.hpp',
                    'Nu/src/search.hpp', 'Nu/tools/collect.py', 'Nu/tools/learning.py',
                    'Nu/tools/teacher/src/main.rs',
                    '.tmp/nu-nokamute/src/board.rs', '.tmp/nu-nokamute/src/hex_grid.rs',
                    'Alpha/vendor/minimax-rs/src/strategies/iterative.rs',
                    'Alpha/vendor/minimax-rs/src/strategies/table.rs',
                    '.tmp/nu-nokamute/LICENSE.md', 'Alpha/vendor/minimax-rs/LICENSE', 'LICENSE',
                    'Nu/work/campaign-v6/corpus/manifest.json']
    for name in source_paths:
        path = ROOT / name
        raw = path.read_bytes()
        result['inputs'][name] = hashlib.sha256(raw).hexdigest()
        snapshot = LAB / 'snapshot' / name
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(raw)
    (LAB / 'evidence.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({key: result[key] for key in ['arenas', 'profile', 'corpus']}, indent=2))

if __name__ == '__main__':
    main()
