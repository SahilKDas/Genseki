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
    parser.add_argument('--games', type=int, default=20)
    parser.add_argument('--milliseconds', type=int, default=250)
    parser.add_argument('--cap', type=int, default=160)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seed-base', type=int, default=71000)
    parser.add_argument('--threads', type=int, default=1)
    parser.add_argument('--threat-plies', type=int, default=0)
    parser.add_argument('--lmr', action='store_true')
    parser.add_argument('--opponent-model', type=Path)
    args = parser.parse_args()
    if args.games <= 0 or args.games % 2 or args.milliseconds < 25 or not 1<=args.threads<=12 or not 4<=args.cap<=256 or not 0<=args.threat_plies<=4: parser.error('invalid bounded match settings')
    if args.output.exists():raise RuntimeError('refusing to overwrite match evidence')
    rows = []
    opponent_hash = hashlib.sha256(args.opponent.read_bytes()).hexdigest()
    model_hash = hashlib.sha256(args.model.read_bytes()).hexdigest()
    engine_hash = hashlib.sha256(args.engine.read_bytes()).hexdigest()
    report=dict(kind='development',games=rows,points=0,expected_games=args.games,completed=False,rejected=False,
                model_sha256=model_hash,engine_sha256=engine_hash,opponent_sha256=opponent_hash,
                milliseconds=args.milliseconds,internal_ms=args.milliseconds-20,threads=args.threads,cap=args.cap,
                repetition_policy=REPETITION_POLICY,threat_plies=args.threat_plies,lmr=args.lmr,seed_base=args.seed_base,
                invocation=[str(args.opponent)],opponent_model_sha256=None)
    report.update(opponent_version='1.0.3' if opponent_hash==NOKAMUTE_SHA256 else None,
                  opponent_revision=NOKAMUTE_REVISION if opponent_hash==NOKAMUTE_SHA256 else None,
                  table_mib=16,background_pondering=False,random_opening=False)
    if args.opponent_model:
        report['invocation']+=['--model',str(args.opponent_model)]
        report['opponent_model_sha256']=hashlib.sha256(args.opponent_model.read_bytes()).hexdigest()
    atomic_json(args.output,report)
    for pair in range(args.games // 2):
        for color in (0, 1):
            from train import resource_guard
            resource_guard()
            nu = UhpProcess([str(args.engine), '--model', str(args.model)])
            try:
                opponent = UhpProcess(report['invocation'])
            except BaseException:
                nu.close();raise
            engines = [nu, opponent] if color == 0 else [opponent, nu]
            rng = random.Random(args.seed_base + pair)
            maximum = 0;moves = [];searches=[];termination='ply_cap';result='Draw';score=.5;timeout_side=None
            try:
                for engine in engines:command(engine, 'newgame Base')
                # Pin the opponent's options and equal single-thread allowance.
                command(nu, f'options Threads {args.threads}')
                command(nu, f'options ThreatPlies {args.threat_plies}')
                command(nu, f'options LateMoveReductions {"True" if args.lmr else "False"}')
                if args.opponent_model:command(opponent,f'options Threads {args.threads}')
                else:
                    command(opponent, f'options set NumThreads {args.threads}')
                    command(opponent, 'options set BackgroundPondering False')
                    command(opponent, 'options set RandomOpening False')
                    command(opponent, 'options set TableSizeMiB 16')
                for ply in range(args.cap):
                    current = engines[ply % 2]
                    if ply < 4:
                        legal, _ = command(nu, 'validmoves');move = rng.choice(legal[0].split(';'))
                    else:
                        seconds = (args.milliseconds - 20) / 1000
                        started=time.perf_counter()
                        try:
                            response, elapsed = command(current, f'bestmove depthorseconds 64 {seconds}', args.milliseconds/1000)
                        except TimeoutError as error:
                            maximum=max(maximum,(time.perf_counter()-started)*1000)
                            raise MoveDeadline('timed move deadline') from error
                        maximum = max(maximum, elapsed * 1000)
                        if elapsed * 1000 > args.milliseconds: raise MoveDeadline('wall-clock deadline')
                        move = response[0]
                        if current is nu:
                            info, _ = command(nu, 'nu-searchinfo')
                            searches.append(dict(ply=ply, move_ms=elapsed*1000, info=info))
                    moves.append(move)
                    game_strings=[command(engine,'play '+move)[0][0] for engine in engines]
                    results=[text.split(';')[1] for text in game_strings]
                    if command(nu,'nu-matchdraw')[0][0]=='True':
                        if not args.opponent_model and results[1-color]!='Draw':raise RuntimeError(f'repetition policy disagreement: {results}')
                        result='Draw';termination='repetition';score=.5;break
                    if results[0] != results[1]:raise RuntimeError(f'result divergence: {results}')
                    if results[0] != 'InProgress':
                        result=results[0];termination='natural'
                        score=.5 if result=='Draw' else float((result=='WhiteWins') == (color==0));break
            except MoveDeadline:
                termination='timeout';score=float(current is not nu);result='Forfeit';timeout_side='Nu' if current is nu else ('Opponent' if args.opponent_model else 'Nokamute')
            except BaseException as error:
                failure=dict(pair=pair,opening_seed=args.seed_base+pair,nu_color='white' if color==0 else 'black',
                             moves=moves,searches=searches,error=repr(error),termination='rejected')
                try:failure['position']=command(nu,'nu-position')[0][0]
                except Exception:pass
                report.update(rejected=True,failure=failure)
                atomic_json(args.output.with_suffix('.failure.json'),failure)
                atomic_json(args.output,report)
                raise
            finally:
                nu.close();opponent.close()
            row=dict(pair=pair, opening_seed=args.seed_base+pair, nu_color='white' if color==0 else 'black',
                     score=score,result=result,termination=termination,max_move_ms=maximum,moves=moves,searches=searches,timeout_side=timeout_side)
            rows.append(row)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            report.update(games=rows,points=sum(r['score'] for r in rows),completed=len(rows)==args.games)
            atomic_json(args.output,report)
            print(f'{len(rows)}/{args.games}: {termination}, Nu score={score}',flush=True)

if __name__ == '__main__': main()
