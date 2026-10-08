"""Summarize pinned completed research evidence without promoting a model."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from genseki.artifacts import portable_value
from evidence import atomic_json, digest


def public_report(report):
    published=portable_value(ROOT,report)
    for name,entry in report.get('frozen',{}).get('files',{}).items():
        if isinstance(entry.get('source'),str):
            published['frozen']['files'][name]['source']=portable_value(ROOT,Path(entry['source']))
    return published


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--campaign',type=Path,required=True)
    parser.add_argument('--benchmark',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise RuntimeError('refusing to replace campaign evidence')
    def read(relative):return json.loads((args.campaign/relative).read_text())
    corpus=read('corpus/manifest.json');verification=read('corpus/verification.json')
    training=read('training/training.json')[0];frozen=read('frozen-screen/manifest.json')
    benchmark=json.loads(args.benchmark.read_text())
    if not corpus['completed'] or verification['accepted']<10000 or not training['completed']:
        raise RuntimeError('incomplete corpus/training')
    if not benchmark['completed'] or not benchmark['memory_limit_verified']:
        raise RuntimeError('incomplete benchmark/memory gate')
    if digest(args.benchmark)!=frozen['benchmark_sha256']:raise RuntimeError('benchmark changed after freeze')
    for name,entry in frozen['files'].items():
        if digest(args.campaign/'frozen-screen'/name)!=entry['sha256']:raise RuntimeError('frozen artifact changed')
    if training['sha256']!=frozen['files']['schema7.nnue']['sha256']:raise RuntimeError('training/model mismatch')
    profiles=[]
    for model in dict.fromkeys(r['model_sha256'] for r in benchmark['records']):
        for threads in (1,2,4):
            rows=[r for r in benchmark['records'] if r['model_sha256']==model and r['threads']==threads]
            complete=[r for r in rows if r.get('legal_reply')]
            depths=[int(r['search'][0].split()[1]) for r in complete]
            nodes=[int(r['search'][0].split()[3]) for r in complete]
            profiles.append(dict(model_sha256=model,threads=threads,roots=len(rows),legal_replies=len(complete),
                timeouts=sum(r['timeout'] for r in rows),engine_exits=sum(r.get('engine_exit',False) for r in rows),
                median_latency_ms=statistics.median(r['latency_ms'] for r in rows),
                maximum_latency_ms=max(r['latency_ms'] for r in rows),
                completed_depth_sum=sum(depths),nodes_sum=sum(nodes),
                maximum_peak_commit_bytes=max(r['memory']['peak_commit'] for r in rows),
                maximum_peak_working_bytes=max(r['memory']['peak_working'] for r in rows),
                maximum_evaluator_plus_table_bytes=max(sum(r['allocations'].values()) for r in rows)))
    screens={}
    for name in ('schema5','schema6','gen1'):
        path=args.campaign/'screens'/(name+'.json');report=json.loads(path.read_text())
        if report['rejected'] or not report['completed'] or len(report['games'])!=20:
            raise RuntimeError('incomplete/rejected screen '+name)
        expected={'engine_sha256':'nu.exe','model_sha256':'schema7.nnue','referee_sha256':'rules.exe',
                  'openings_sha256':'openings.json','opponent_sha256':'gen1.exe' if name=='gen1' else 'nu.exe'}
        if any(report[k]!=frozen['files'][v]['sha256'] for k,v in expected.items()):raise RuntimeError('screen pins differ')
        if name!='gen1' and report['opponent_model_sha256']!=frozen['files'][name+'.nnue']['sha256']:
            raise RuntimeError('opponent model mismatch')
        for key,value in dict(threads=1,table_mib=16,internal_ms=230,milliseconds=250,cap=160,depth_limit=64).items():
            if report[key]!=value:raise RuntimeError('screen settings differ')
        rows=report['games'];scores=Counter(r['score'] for r in rows)
        screens[name]=dict(report_sha256=digest(path),points=report['points'],games=20,
            wins=scores[1],draws=scores[.5],losses=scores[0],
            terminations=dict(Counter(r['termination'] for r in rows)),
            maximum_move_ms=max(r['max_move_ms'] for r in rows),
            games_summary=[{k:r[k] for k in ('pair','opening_seed','nu_color','score','result','termination','max_move_ms','timeout_side')} for r in rows])
    training={k:v for k,v in training.items() if k!='curves'}
    gen1=benchmark['gen1_records']
    report=dict(version=1,qualification_run=False,promoted=False,defaults_changed=False,
        corpus=corpus,exclusion_verification=verification,training=training,frozen=frozen,
        benchmark=dict(report_sha256=digest(args.benchmark),profiles=profiles,costs=benchmark['costs'],
            gen1_roots=len(gen1),gen1_timeouts=benchmark['gen1_timeouts'],
            gen1_diagnostic_failures=sum('diagnostic_error' in r for r in gen1),
            gen1_completed_depth_sum=sum(r.get('completed_depth',0) or 0 for r in gen1),
            gen1_nodes_sum=sum(r.get('nodes',0) or 0 for r in gen1),
            gen1_verbose_for_diagnostics=True,
            gen1_peak_commit_bytes=max(r['memory']['peak_commit'] for r in gen1)),screens=screens,
        limitations=['Development screens are not sealed qualification or promotion.',
                    'Capped draws are adjudications, not natural outcomes.',
                    'Schema 6 multithreaded heap-corruption exits and deadline failures remain unresolved.',
                    'Benchmark attempts before benchmark-v4 are incomplete or have invalid Gen 1 time spelling.',
                    'Gen 1 profiling enables diagnostic verbosity; matches do not.'])
    atomic_json(args.output,public_report(report))
    print(json.dumps({name:r['points'] for name,r in screens.items()}))


if __name__=='__main__':main()
