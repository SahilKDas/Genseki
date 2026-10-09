"""Mirrored development matches; never silently score protocol divergence."""
import argparse
import hashlib
import json
from pathlib import Path
import random
import sys
import time
from evidence import REPETITION_POLICY, atomic_json, NOKAMUTE_REVISION, NOKAMUTE_SHA256
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from genseki.uhp import UhpProcess
from genseki.gauntlet import SEARCH_DEPTH_LIMIT
from research_job import StageStopped

VALIDATION_POLICY = 'three-reconstructed-boards-repetition-v1'
MEMORY_POLICY = 'configure-before-newgame-v1'


def validate_boards(referee, states, repeated=False):
    headers=[]; positions=[]
    for state in states:
        fields=state.split(';')
        if len(fields)<3:raise RuntimeError('malformed replay')
        if repeated:
            if fields[1] not in ('InProgress','Draw'):raise RuntimeError('invalid repetition result')
            # The rules service has no repetition rule. This explicit, frozen arena
            # policy permits only a known repetition Draw, not arbitrary divergence.
            fields[1]='InProgress'
        normalized=';'.join(fields)
        positions.append(command(referee,'genseki-validate-game '+normalized)[0][0])
        headers.append(fields[:3])
    if any(h!=headers[0] for h in headers[1:]) or any(p!=positions[0] for p in positions[1:]):
        raise RuntimeError('reconstructed board divergence')
    return positions[0]

class MoveDeadline(TimeoutError):
    pass

def command(engine, text, timeout=5):
    lines, elapsed = engine.command(text, timeout)
    if any(line.startswith('err ') or line.startswith('invalidmove') for line in lines):
        raise RuntimeError(f'protocol/rules divergence: {text}: {lines}')
    return [x for x in lines if x != 'ok'], elapsed

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', type=Path, default=ROOT/'build-nu/nu.exe')
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--opponent', type=Path, required=True)
    parser.add_argument('--referee', type=Path, required=True)
    parser.add_argument('--games', type=int, default=20)
    parser.add_argument('--milliseconds', type=int, default=250)
    parser.add_argument('--cap', type=int, default=160)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed-base', type=int, default=71000)
    parser.add_argument('--openings',type=Path)
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--threat-plies', type=int, default=0)
    parser.add_argument('--lmr', action='store_true')
    parser.add_argument('--deadline-guard',action='store_true')
    parser.add_argument('--cooperative-ordering',action='store_true')
    parser.add_argument('--root-pvs',action='store_true')
    parser.add_argument('--candidate-only-selectivity',action='store_true')
    parser.add_argument('--hybrid',action='store_true')
    parser.add_argument('--hybrid-weight',type=int,default=100)
    parser.add_argument('--hybrid-terms',type=int,default=63)
    parser.add_argument('--opponent-model', type=Path)
    parser.add_argument('--resume',action='store_true')
    args = parser.parse_args()
    if not 0<=args.hybrid_weight<=200 or not 0<=args.hybrid_terms<=127:parser.error('invalid hybrid settings')
    openings=json.loads(args.openings.read_text())['openings'] if args.openings else None
    if openings is not None and (len(openings)*2!=args.games or any(len(row['moves'])!=4 for row in openings)):
        raise RuntimeError('opening manifest must contain one four-ply opening per mirrored pair')
    if args.games <= 0 or args.games % 2 or args.milliseconds < 25 or not 1<=args.threads<=12 or not 4<=args.cap<=256 or not 0<=args.threat_plies<=4: parser.error('invalid bounded match settings')
    if args.output.exists() and not args.resume:raise RuntimeError('refusing to overwrite match evidence')
    saved=json.loads(args.output.read_text()) if args.output.exists() else None
    rows = []
    opponent_hash = hashlib.sha256(args.opponent.read_bytes()).hexdigest()
    model_hash = hashlib.sha256(args.model.read_bytes()).hexdigest()
    engine_hash = hashlib.sha256(args.engine.read_bytes()).hexdigest()
    report=dict(kind='development',games=rows,points=0,expected_games=args.games,completed=False,rejected=False,
                model_sha256=model_hash,engine_sha256=engine_hash,opponent_sha256=opponent_hash,
                milliseconds=args.milliseconds,internal_ms=args.milliseconds-20,threads=args.threads,cap=args.cap,
                repetition_policy=REPETITION_POLICY,threat_plies=args.threat_plies,lmr=args.lmr,seed_base=args.seed_base,
                invocation=[str(args.opponent)],opponent_model_sha256=None)
    report.update(referee_sha256=hashlib.sha256(args.referee.read_bytes()).hexdigest(),
                  opponent_search_policy=('candidate-selectivity-v1' if args.candidate_only_selectivity else 'equal-nu-search-v1') if args.opponent_model else 'external-engine-v1',
                  hybrid=args.hybrid,hybrid_weight=args.hybrid_weight,hybrid_terms=args.hybrid_terms,
                  validation_policy=VALIDATION_POLICY,depth_limit=SEARCH_DEPTH_LIMIT,
                  memory_policy=MEMORY_POLICY,
                  openings_sha256=hashlib.sha256(args.openings.read_bytes()).hexdigest() if args.openings else None)
    report.update(deadline_guard=args.deadline_guard,cooperative_ordering=args.cooperative_ordering,
                  candidate_only_selectivity=args.candidate_only_selectivity,root_pvs=args.root_pvs)
    report.update(opponent_version='1.0.3' if opponent_hash==NOKAMUTE_SHA256 else None,
                  opponent_revision=NOKAMUTE_REVISION if opponent_hash==NOKAMUTE_SHA256 else None,
                  table_mib=16,background_pondering=False,random_opening=False)
    if args.opponent_model:
        report['invocation']+=['--model',str(args.opponent_model)]
        report['opponent_model_sha256']=hashlib.sha256(args.opponent_model.read_bytes()).hexdigest()
    if saved is not None:
        keys=('kind','expected_games','engine_sha256','model_sha256','opponent_sha256','opponent_model_sha256','referee_sha256','validation_policy','memory_policy','depth_limit','openings_sha256','milliseconds','internal_ms','threads','cap','repetition_policy','threat_plies','lmr','seed_base','table_mib','background_pondering','random_opening')
        if saved.get('rejected') or any(saved.get(k)!=report.get(k) for k in keys):raise RuntimeError('arena resume identity/settings mismatch or rejected run')
        if any(saved.get(k,False)!=report[k] for k in ('deadline_guard','cooperative_ordering','candidate_only_selectivity','root_pvs')):
            raise RuntimeError('candidate search settings mismatch')
        previous_policy=saved.get('opponent_search_policy')
        if previous_policy is None:
            if args.opponent_model and (args.threat_plies or args.lmr):raise RuntimeError('legacy opponent search settings are not equivalent')
        elif previous_policy!=report['opponent_search_policy']:raise RuntimeError('opponent search policy mismatch')
        if any(saved.get(k)!=report[k] for k in ('hybrid','hybrid_weight','hybrid_terms')):raise RuntimeError('hybrid resume settings mismatch')
        rows=saved['games']
        if len(rows)>args.games or any(g.get('pair')!=i//2 or g.get('opening_seed')!=(openings[i//2]['seed'] if openings else args.seed_base+i//2) or g.get('nu_color')!=('white' if i%2==0 else 'black') for i,g in enumerate(rows)):raise RuntimeError('arena resume game prefix mismatch')
        if saved.get('points')!=sum(g['score'] for g in rows):raise RuntimeError('arena resume total mismatch')
        report.update(games=rows,points=sum(g['score'] for g in rows),completed=len(rows)==args.games)
        if report['completed']:return
    atomic_json(args.output,report)
    for pair in range(args.games // 2):
        for color in (0, 1):
            if pair*2+color<len(rows):continue
            if args.openings and hashlib.sha256(args.openings.read_bytes()).hexdigest()!=report['openings_sha256']:
                raise RuntimeError('immutable opening manifest changed')
            if hashlib.sha256(args.referee.read_bytes()).hexdigest()!=report['referee_sha256'] or hashlib.sha256(args.engine.read_bytes()).hexdigest()!=engine_hash or hashlib.sha256(args.model.read_bytes()).hexdigest()!=model_hash or hashlib.sha256(args.opponent.read_bytes()).hexdigest()!=opponent_hash or (args.opponent_model and hashlib.sha256(args.opponent_model.read_bytes()).hexdigest()!=report['opponent_model_sha256']):raise RuntimeError('immutable arena artifact changed')
            from train import resource_guard
            resource_guard()
            nu = UhpProcess([str(args.engine), '--model', str(args.model)])
            try:
                opponent = UhpProcess(report['invocation'])
            except BaseException:
                nu.close();raise
            engines = [nu, opponent] if color == 0 else [opponent, nu]
            try:referee=UhpProcess([str(args.referee)])
            except BaseException:
                nu.close();opponent.close();raise
            opening_seed=openings[pair]['seed'] if openings else args.seed_base+pair
            rng = random.Random(opening_seed)
            maximum = 0;moves = [];searches=[];termination='ply_cap';result='Draw';score=.5;timeout_side=None
            try:
                # Pin the opponent's options and equal single-thread allowance.
                command(nu, f'options Threads {args.threads}')
                command(nu, 'options TableMiB 16')
                command(nu, 'options BackgroundPondering False')
                command(nu, f'options ThreatPlies {args.threat_plies}')
                command(nu, f'options LateMoveReductions {"True" if args.lmr else "False"}')
                if args.deadline_guard:command(nu,'options DeadlineGuard True')
                if args.cooperative_ordering:command(nu,'options CooperativeOrdering True')
                if args.root_pvs:command(nu,'options RootPVS True')
                if args.hybrid:
                    command(nu,'options HybridEvaluation True')
                    command(nu,f'options HybridWeight {args.hybrid_weight}')
                    command(nu,f'options HybridTerms {args.hybrid_terms}')
                if args.opponent_model:
                    command(opponent,f'options Threads {args.threads}')
                    command(opponent,'options TableMiB 16')
                    command(opponent,'options BackgroundPondering False')
                    command(opponent,f'options ThreatPlies {0 if args.candidate_only_selectivity else args.threat_plies}')
                    command(opponent,f'options LateMoveReductions {"True" if args.lmr and not args.candidate_only_selectivity else "False"}')
                else:
                    command(opponent, f'options set NumThreads {args.threads}')
                    command(opponent, 'options set BackgroundPondering False')
                    command(opponent, 'options set RandomOpening False')
                    command(opponent, 'options set TableSizeMiB 16')
                initial=[command(engine,'newgame Base')[0][0] for engine in [*engines,referee]]
                validate_boards(referee,initial)
                for ply in range(args.cap):
                    from research_job import check_deadline
                    check_deadline()
                    current = engines[ply % 2]
                    if ply < 4:
                        if openings is not None:move=openings[pair]['moves'][ply]
                        else:
                            legal, _ = command(nu, 'validmoves');move = rng.choice(legal[0].split(';'))
                    else:
                        seconds = (args.milliseconds - 20) / 1000
                        started=time.perf_counter()
                        try:
                            response, elapsed = command(current, f'bestmove depthorseconds {SEARCH_DEPTH_LIMIT} {seconds}', args.milliseconds/1000)
                        except TimeoutError as error:
                            maximum=max(maximum,(time.perf_counter()-started)*1000)
                            raise MoveDeadline('timed move deadline') from error
                        maximum = max(maximum, elapsed * 1000)
                        if elapsed * 1000 > args.milliseconds: raise MoveDeadline('wall-clock deadline')
                        move = response[0]
                        if current is nu:
                            info, _ = command(nu, 'nu-searchinfo')
                            record=dict(ply=ply, move_ms=elapsed*1000, info=info)
                            if args.deadline_guard:
                                timing,_=command(nu,'nu-timing');record['timing']=timing
                            searches.append(record)
                    moves.append(move)
                    game_strings=[command(engine,'play '+move)[0][0] for engine in engines]
                    results=[text.split(';')[1] for text in game_strings]
                    referee_game=command(referee,'play '+move)[0][0]
                    repeated=command(nu,'nu-matchdraw')[0][0]=='True' and referee_game.split(';')[1]=='InProgress'
                    agreed=validate_boards(referee,[*game_strings,referee_game],repeated)
                    if ply==3 and openings and agreed!=openings[pair]['position']:
                        raise RuntimeError('opening manifest position mismatch')
                    if repeated:
                        if not args.opponent_model and results[1-color]!='Draw':raise RuntimeError(f'repetition policy disagreement: {results}')
                        result='Draw';termination='repetition';score=.5;break
                    if results[0] != results[1]:raise RuntimeError(f'result divergence: {results}')
                    if results[0] != 'InProgress':
                        result=results[0];termination='natural'
                        score=.5 if result=='Draw' else float((result=='WhiteWins') == (color==0));break
            except MoveDeadline:
                termination='timeout';score=float(current is not nu);result='Forfeit';timeout_side='Nu' if current is nu else 'Opponent'
            except (KeyboardInterrupt,StageStopped) as error:
                interrupted=dict(pair=pair,opening_seed=opening_seed,moves=moves,searches=searches,
                                 reason=type(error).__name__)
                atomic_json(args.output.with_name(args.output.stem+f'.interrupted-{time.time_ns()}.json'),interrupted)
                atomic_json(args.output,report)
                raise
            except BaseException as error:
                failure=dict(pair=pair,opening_seed=opening_seed,nu_color='white' if color==0 else 'black',
                             moves=moves,searches=searches,error=repr(error),termination='rejected')
                try:failure['position']=command(nu,'nu-position')[0][0]
                except Exception:pass
                report.update(rejected=True,failure=failure)
                atomic_json(args.output.with_suffix('.failure.json'),failure)
                atomic_json(args.output,report)
                raise
            finally:
                nu.close();opponent.close();referee.close()
            row=dict(pair=pair, opening_seed=opening_seed, nu_color='white' if color==0 else 'black',
                     score=score,result=result,termination=termination,max_move_ms=maximum,moves=moves,searches=searches,timeout_side=timeout_side)
            rows.append(row)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            report.update(games=rows,points=sum(r['score'] for r in rows),completed=len(rows)==args.games)
            atomic_json(args.output,report)
            print(f'{len(rows)}/{args.games}: {termination}, Nu score={score}',flush=True)

if __name__ == '__main__':
    from research_job import run
    run(main)
