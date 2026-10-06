"""Mirrored development/one-use qualification runner, with atomic partial evidence."""
from __future__ import annotations
import argparse
import json
import random
import secrets
import time
from pathlib import Path
from common import ROOT,UhpProcess,command,atomic,digest,guard,acquire_job

def pin_alpha(engine):
    options,_=command(engine,'options')
    names={line.split(';')[0] for line in options}
    thread=next((name for name in ('NumThreads','Threads','MaxThreads') if name in names),None)
    if thread is None:raise RuntimeError('cannot verify Alpha thread allowance')
    command(engine,'options set '+thread+' 1')
    for name in ('BackgroundPondering','RandomOpening'):
        if name in names:command(engine,'options set '+name+' False')
    effective,_=command(engine,'options')
    values={line.split(';')[0]:line.split(';')[2] for line in effective if len(line.split(';'))>=3}
    if values.get(thread)!='1':raise RuntimeError('Alpha thread setting ineffective')
    for name in ('BackgroundPondering','RandomOpening'):
        if name in names and values.get(name,'').lower()!='false':raise RuntimeError('Alpha option setting ineffective: '+name)
    return effective

def verify_state(checker,rules,actual,expected):
    if actual==expected:return
    if actual.split(';')[:3]!=expected.split(';')[:3]:raise RuntimeError(f'rules result/turn divergence: {actual}: {expected}')
    # UHP permits different reference stones for the same destination.
    command(checker,'newgame '+actual)
    replay,_=command(checker,'iota-position');authority,_=command(rules,'iota-position')
    if replay!=authority:raise RuntimeError('replayed rules state divergence')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--model',required=True)
    p.add_argument('--mode',choices=['alphabeta','mcts'],default='alphabeta')
    p.add_argument('--games',type=int,default=20)
    p.add_argument('--minutes',type=float,default=30)
    p.add_argument('--seed',type=int,default=2701)
    p.add_argument('--alpha',default=str(ROOT.parent/'build/genseki.exe'))
    p.add_argument('--engine',type=Path,default=ROOT/'build/iota.exe')
    p.add_argument('--qualification',action='store_true')
    p.add_argument('--output',required=True)
    args=p.parse_args()
    if args.games<2 or args.games%2 or args.minutes<=0:p.error('positive even game count and time budget required')
    if args.qualification and args.games!=100:p.error('qualification requires exactly 100 games')
    job=acquire_job();exe=args.engine;out=Path(args.output)
    if out.exists():raise RuntimeError('refusing to overwrite match evidence')
    identity=dict(model=digest(args.model),iota=digest(exe),alpha=digest(args.alpha),mode=args.mode,
                  move_ms=250,internal_ms=230,alpha_request_ms=230,iota_request_ms=250,
                  threads=1,cap=160,repetition=3,ponder=False)
    marker=ROOT/'work/qualification'/f"{identity['model']}-{identity['iota']}-{args.mode}.json"
    if args.qualification:
        marker.parent.mkdir(parents=True,exist_ok=True)
        # Exclusive creation occurs before opening seeds are generated; failures consume the attempt.
        with marker.open('x',encoding='utf-8') as f:json.dump(dict(identity=identity,status='frozen'),f)
        seed=secrets.randbits(64)
    else:seed=args.seed
    report=dict(identity=identity,seed=seed,qualification=args.qualification,games=[],complete=False,points=0,valid=True)
    deadline=time.monotonic()+args.minutes*60;atomic(out,report)
    try:
        for g in range(args.games):
            if time.monotonic()>deadline-1:break
            guard();pair=g//2;rng=random.Random(seed+pair);color='w' if g%2==0 else 'b'
            players={};rules=None;checker=None
            try:
                players['iota']=UhpProcess([str(exe),'--model',args.model])
                players['alpha']=UhpProcess([args.alpha])
                rules=UhpProcess([str(exe)])
                checker=UhpProcess([str(exe)])
            except BaseException:
                for engine in players.values():engine.close()
                for engine in (rules,checker):
                    if engine is not None:engine.close()
                raise
            record=dict(pair=pair,opening_seed=seed+pair,iota_color=color,moves=[],times=[],reason=None,score=0)
            try:
                command(players['iota'],'options set Search '+args.mode)
                # Pin effective Alpha options; fail closed if threading cannot be fixed.
                record['alpha_options']=pin_alpha(players['alpha'])
                command(players['iota'],'options set Threads 1')
                for engine in [*players.values(),rules]:command(engine,'newgame Base')
                seen={};game='Base;NotStarted;White[1]';record['reason']='ply_cap'
                for ply in range(160):
                    if time.monotonic()>deadline-1:record['reason']='campaign_deadline';break
                    side='w' if game.split(';')[2].startswith('White') else 'b';actor='iota' if side==color else 'alpha'
                    if args.qualification:
                        legal,_=command(rules,'validmoves');expected=set(range(len(legal[0].split(';'))))
                        for engine in players.values():
                            choices,_=command(engine,'validmoves');actual=set()
                            for choice in choices[0].split(';'):
                                index,_=command(rules,'iota-index '+choice);actual.add(int(index[0]))
                            if actual!=expected:raise RuntimeError('legal-move divergence')
                    if ply<4:
                        legal,_=command(rules,'validmoves');move=rng.choice(legal[0].split(';'));elapsed=0
                    else:
                        request='00:00:00.250' if actor=='iota' else '00:00:00.230'
                        started=time.perf_counter()
                        try:lines,elapsed=command(players[actor],'bestmove time '+request,.250);move=lines[-1]
                        except TimeoutError:
                            record.update(reason='timeout',failed_actor=actor,failed_move_seconds=time.perf_counter()-started)
                            record['score']=0 if actor=='iota' else 1;break
                        except RuntimeError:
                            record.update(reason='protocol_failure',failed_actor=actor)
                            record['score']=0 if actor=='iota' else 1;report['valid']=False;break
                        if elapsed>.250:
                            record.update(reason='timeout',failed_actor=actor,failed_move_seconds=elapsed)
                            record['score']=0 if actor=='iota' else 1;break
                    record['times'].append(dict(actor=actor,seconds=elapsed))
                    try:
                        current,_=command(rules,'pass' if move=='pass' else 'play '+move);game=current[0]
                    except RuntimeError:record['reason']='illegal_move';record['score']=0 if actor=='iota' else 1;report['valid']=False;break
                    record['moves'].append(move)
                    for engine in players.values():
                        response,_=command(engine,'pass' if move=='pass' else 'play '+move)
                        verify_state(checker,rules,response[0],game)
                    result=game.split(';')[1]
                    if result in ('WhiteWins','BlackWins','Draw'):
                        record['reason']='terminal';record['score']=.5 if result=='Draw' else int((result=='WhiteWins')==(color=='w'));break
                    canonical,_=command(rules,'iota-repetition');seen[canonical[0]]=seen.get(canonical[0],0)+1
                    if seen[canonical[0]]>=3:record['reason']='repetition';record['score']=.5;break
                if record['reason']=='ply_cap':record['score']=.5
                record['final_game']=game
            except Exception as error:
                record['reason']='divergence_or_failure';record['error']=repr(error);report['valid']=False
            finally:
                for engine in [*players.values(),rules,checker]:engine.close()
            report['games'].append(record);report['points']+=record['score'];atomic(out,report)
            print(f"game {g+1}: {record['reason']} score={record['score']}",flush=True)
            if not report['valid'] or record['reason']=='campaign_deadline':break
        report['complete']=len(report['games'])==args.games and all(g['reason']!='campaign_deadline' for g in report['games'])
        report['passed']=args.qualification and report['complete'] and report['valid'] and report['points']>=50
        report['natural_games']=sum(g['reason']=='terminal' for g in report['games'])
        report['natural_points']=sum(g['score'] for g in report['games'] if g['reason']=='terminal')
        report['timeout_points']=sum(g['score'] for g in report['games'] if g['reason']=='timeout')
        report['timeouts']={actor:sum(g.get('failed_actor')==actor and g['reason']=='timeout' for g in report['games']) for actor in ('iota','alpha')}
        if identity['iota']!=digest(exe) or identity['model']!=digest(args.model) or identity['alpha']!=digest(args.alpha):report['valid']=False;report['passed']=False
        atomic(out,report)
        if args.qualification:atomic(marker,dict(identity=identity,status='consumed',report=str(out),passed=report['passed']))
    finally:atomic(out,report)

if __name__=='__main__':main()
