"""Freeze replay-derived Base Hive tactics; estimates never become rule proofs."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from genseki.resources import job_lock, heavy_job_path, team_job_path, available_ram
from genseki.uhp import UhpProcess
from genseki.artifacts import sha256_file


def position_key(position):
    fields=position.split('|')
    if len(fields)!=6 or fields[0]!='G1':raise ValueError('expected G1 position')
    cells=[]
    for entry in fields[5].split(';'):
        if entry:
            xy,stack=entry.split('=')
            q,r=map(int,xy.split(','))
            cells.append((q,r,','.join(piece[:2] for piece in stack.split(','))))
    forms=[]
    for mirror in (False,True):
        transformed=[(r,q,s) if mirror else (q,r,s) for q,r,s in cells]
        for rotation in range(6):
            origin_q=min((q for q,r,s in transformed),default=0)
            origin_r=min((r for q,r,s in transformed),default=0)
            forms.append(sorted((q-origin_q,r-origin_r,s) for q,r,s in transformed))
            transformed=[(-r,q+r,s) for q,r,s in transformed]
    queens={piece[:2] for entry in fields[5].split(';') if entry for piece in entry.split('=')[1].split(',')}
    phase=[4 if color+'Q' in queens else min(int(fields[index]),4) for color,index in (('w',3),('b',4))]
    return hashlib.sha256(json.dumps([fields[1],phase,min(forms)],separators=(',',':')).encode()).hexdigest()


def candidate_sources(reviews,arenas):
    candidates=[];sources=[]
    for path in [*reviews,*arenas]:
        path=path.resolve()
        if not path.is_relative_to(ROOT) or any(p.lower()=='iota' for p in path.parts):
            raise ValueError('sources must be inside the repository and outside Iota')
        if path.stat().st_size>64*1024**2:raise ValueError('source exceeds 64 MiB bound')
        identity=sha256_file(path);document=json.loads(path.read_text(encoding='utf-8'))
        sources.append(dict(path=path.relative_to(ROOT).as_posix(),sha256=identity))
        if path in [p.resolve() for p in reviews]:
            if document.get('version')!=1:raise ValueError('unsupported review export')
            for entry in document.get('moves',[]):
                game=entry.get('before','')
                if not game.startswith('Base;'):continue
                candidates.append(dict(game_string=game,source_game=identity,
                    source_id=identity,source_ply=entry['ply'],outcome=None,
                    claimed_tactics=[f['kind'] for f in entry.get('facts',[]) if f['kind'] in ('missed_win','winning_reply','mandatory_defense')],
                    estimates=[dict(source='review-search',score=entry['root_score'],orientation='side-to-move',completed_depth=entry.get('completed_depth'))]
                        if entry.get('status') in ('complete','tactics_incomplete') and entry.get('root_score') is not None else []))
        else:
            if document.get('config',{}).get('stage')!='development' or not document.get('valid',True):
                raise ValueError('only valid declared development losses are accepted')
            for game in document.get('games',[]):
                if game.get('score')!=0 or game.get('termination')!='natural':continue
                moves=game['moves']
                for ply in range(max(4,len(moves)-12),len(moves)):
                    candidates.append(dict(game_string='Base;;;'+ ';'.join(moves[:ply]),
                        source_game=f'{identity}:{game["index"]}',source_id=identity,source_ply=ply,
                        natural_game='Base;;;'+ ';'.join(moves),
                        outcome=None,claimed_tactics=['development-loss'],estimates=[]))
    return candidates,sources


class ProofInterrupted(RuntimeError):pass


def checked(engine,text,deadline):
    if time.monotonic()>=deadline:raise ProofInterrupted
    lines,_=engine.command(text,min(5,max(.001,deadline-time.monotonic())))
    if any(line.startswith(('err ','invalidmove')) for line in lines):raise ValueError('rules replay rejected')
    return [line for line in lines if line!='ok']


def load_game(engine,game,deadline):
    fields=game.split(';')
    if fields[0]!='Base':raise ValueError('only Base Hive fixtures are supported')
    state=checked(engine,'newgame Base',deadline)[0]
    for move in fields[3:]:
        if move:state=checked(engine,'play '+move,deadline)[0]
    if len(fields)>=3 and fields[1] and fields[2] and fields[1:3]!=state.split(';')[1:3]:
        raise ValueError('source state disagrees with legal replay')
    return state


def surround_result(position):
    cells={};queens={}
    for entry in position.split('|')[5].split(';'):
        if entry:
            xy,stack=entry.split('=');cell=tuple(map(int,xy.split(',')));cells[cell]=stack
            for piece in stack.split(','):
                if piece in ('wQ','bQ'):queens[piece[0]]=cell
    surrounded={color:all((q+dq,r+dr) in cells for dq,dr in ((1,0),(0,1),(-1,1),(-1,0),(0,-1),(1,-1)))
                for color,(q,r) in queens.items()}
    if surrounded.get('w') and surrounded.get('b'):return 'Draw'
    if surrounded.get('w'):return 'BlackWins'
    if surrounded.get('b'):return 'WhiteWins'
    return 'InProgress'


def prove(engine,game,budget_ms,stage_deadline):
    deadline=min(stage_deadline,time.monotonic()+budget_ms/1000)
    exposures=set();position=None
    def command(text):
        if time.monotonic()>=deadline:raise ProofInterrupted
        lines,_=engine.command(text,min(5,max(.001,deadline-time.monotonic())))
        if any(line.startswith(('err ','invalidmove')) for line in lines):raise ValueError('rules replay rejected')
        return [line for line in lines if line!='ok']
    def win(state,white):return state.split(';')[1]==('WhiteWins' if white else 'BlackWins')
    def key():
        pos=command('genseki-position')[0];value=position_key(pos);exposures.add(value);return pos
    started=time.monotonic()
    proof=dict(status='unknown',kind='unknown',winning_moves=[],safe_moves=[],legal_moves=[],
               losing_witnesses=[],budget_ms=budget_ms,all_roots_checked=False)
    try:
        state=load_game(engine,game,deadline);game=state
        position=key();white=state.split(';')[2].startswith('White[')
        if state.split(';')[1] not in ('NotStarted','InProgress'):raise ValueError('fixture root is terminal')
        proof['legal_moves']=sorted(command('validmoves')[0].split(';'))
        children=dict(line.split('\t',1) for line in command('genseki-children'))
        if set(children)!=set(proof['legal_moves']):raise ValueError('incomplete legal child enumeration')
        for move,child_position in children.items():
            exposures.add(position_key(child_position))
            if surround_result(child_position)==('WhiteWins' if white else 'BlackWins'):
                # Corroborate every winning witness with the referee's result.
                child=command('play '+move)[0]
                if not win(child,white):raise ValueError('surround witness disagrees with referee')
                command('undo');proof['winning_moves'].append(move)
        if proof['winning_moves']:
            proof.update(status='complete',kind='immediate_win',all_roots_checked=True)
            proof['winning_moves'].sort()
            proof['elapsed_ms']=(time.monotonic()-started)*1000
            return dict(game_string=game,position=position,position_key=position_key(position),exposures=sorted(exposures),proof=proof)
        for move in proof['legal_moves']:
            child_position=children[move];result=surround_result(child_position)
            if result==('BlackWins' if white else 'WhiteWins'):
                proof['losing_witnesses'].append(dict(move=move,reply=None,child_position=child_position))
            elif result=='Draw':proof['safe_moves'].append(move)
            else:
                command('play '+move)
                losing=None
                replies=dict(line.split('\t',1) for line in command('genseki-children'))
                for reply,reply_position in sorted(replies.items()):
                    exposures.add(position_key(reply_position))
                    if surround_result(reply_position)==('BlackWins' if white else 'WhiteWins'):
                        final=command('play '+reply)[0]
                        if not win(final,not white):raise ValueError('reply witness disagrees with referee')
                        command('undo');losing=reply;break
                if losing is None:proof['safe_moves'].append(move)
                else:proof['losing_witnesses'].append(dict(move=move,reply=losing,child_position=child_position))
                command('undo')
        proof.update(status='complete',all_roots_checked=True,
            kind='immediate_win' if proof['winning_moves'] else
                 'mandatory_defense' if proof['safe_moves'] and proof['losing_witnesses'] else 'none')
    except (ProofInterrupted,TimeoutError):
        # Stop using this transport after timeout: its next reply may be stale.
        proof.update(status='unknown',kind='unknown',winning_moves=[],safe_moves=[],all_roots_checked=False)
    proof['elapsed_ms']=(time.monotonic()-started)*1000
    return dict(game_string=game,position=position,position_key=position_key(position) if position else None,
                exposures=sorted(exposures),proof=proof)


def split_records(records):
    # Union source games with opening families before assigning either split.
    parent={}
    def find(key):
        parent.setdefault(key,key)
        if parent[key]!=key:parent[key]=find(parent[key])
        return parent[key]
    for record in records:
        game='game:'+record['source_game'];family=record['opening_family']
        a,b=find(game),find(family)
        if a!=b:parent[max(a,b)]=min(a,b)
    families={}
    for record in records:families.setdefault(find(record['opening_family']),set()).add(record['opening_family'])
    for record in records:
        record['opening_family']=min(families[find(record['opening_family'])])
        record['split']='heldout' if int(hashlib.sha256(record['opening_family'].encode()).hexdigest()[:8],16)%5==0 else 'development'
    exposure_splits={}
    for record in records:
        for key in record['exposures']:exposure_splits.setdefault(key,set()).add(record['split'])
    overlaps={key for key,splits in exposure_splits.items() if len(splits)>1}
    kept=[];excluded=[];seen=set()
    for record in records:
        if overlaps.intersection(record['exposures']):excluded.append(dict(id=record['id'],reason='cross-split-position-overlap'))
        elif (record['split'],record['position_key']) in seen:excluded.append(dict(id=record['id'],reason='duplicate-position'))
        else:kept.append(record);seen.add((record['split'],record['position_key']))
    return kept,excluded


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--review',type=Path,nargs='*',default=[]);p.add_argument('--arena',type=Path,nargs='*',default=[])
    p.add_argument('--rules',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-positions',type=int,default=32);p.add_argument('--seconds',type=int,default=120)
    p.add_argument('--proof-ms',type=int,default=2000)
    args=p.parse_args()
    if not 1<=args.seconds<=7200 or not 1<=args.max_positions<=1000 or not 1<=args.proof_ms<=10000:p.error('bounded stage required')
    if not args.review and not args.arena:p.error('at least one source required')
    if args.output.exists():p.error('frozen fixture output already exists')
    candidates,sources=candidate_sources(args.review,args.arena)
    # Interleave source games so a bounded stage cannot consume only one family.
    groups={}
    for candidate in candidates:groups.setdefault(candidate['source_game'],[]).append(candidate)
    for group in groups.values():group.sort(key=lambda c:-c['source_ply'])
    candidates=[group[index] for index in range(max((len(g) for g in groups.values()),default=0))
                for name,group in sorted(groups.items()) if index<len(group)]
    deadline=time.monotonic()+args.seconds
    records=[]
    with job_lock(team_job_path(ROOT)),job_lock(heavy_job_path(ROOT)):
        if os.name=='nt':
            kernel=ctypes.windll.kernel32;kernel.GetCurrentProcess.restype=ctypes.c_void_p
            kernel.SetPriorityClass.argtypes=[ctypes.c_void_p,ctypes.c_ulong]
            kernel.SetPriorityClass(kernel.GetCurrentProcess(),0x40)
        if available_ram()<512*1024**2 or shutil.disk_usage(ROOT).free<512*1024**2:raise RuntimeError('resource reserve unavailable')
        for candidate in candidates[:args.max_positions]:
            if time.monotonic()>=deadline:break
            # Fresh process per record guarantees an interrupted proof cannot
            # contaminate the next record's state or response stream.
            with_engine=UhpProcess([str(args.rules.resolve())])
            try:
                prefix=candidate['game_string'].split(';')[3:7]
                checked(with_engine,'newgame Base',deadline)
                for move in prefix:
                    if move:checked(with_engine,'play '+move,deadline)
                opening=checked(with_engine,'genseki-position',deadline)[0]
                if candidate.get('natural_game'):
                    terminal=load_game(with_engine,candidate['natural_game'],deadline).split(';')[1]
                    if terminal not in ('WhiteWins','BlackWins','Draw'):raise ValueError('natural source outcome did not replay to a terminal state')
                    candidate['outcome']=dict(source='natural-game',result=terminal)
                verified=prove(with_engine,candidate['game_string'],args.proof_ms,deadline)
                if verified['position'] is None:continue
            finally:with_engine.close()
            record=dict(candidate,**{k:v for k,v in verified.items() if k!='game_string'})
            record['game_string']=verified['game_string']
            record['opening_family']='opening-'+position_key(opening)
            record['id']=hashlib.sha256((candidate['source_game']+':'+str(candidate['source_ply'])).encode()).hexdigest()
            records.append(record)
    records,excluded=split_records(records)
    payload=dict(schema_version=1,sources=sources,referee_sha256=sha256_file(args.rules),
                 referee_provenance='imported-binary until verified source manifest is supplied',
                 records=records,exclusions=excluded,split_policy='opening families; remove all cross-split exposures; no heldout tuning',
                 counts={split:sum(r['split']==split and r['proof']['status']=='complete' and r['proof']['kind'] in ('immediate_win','mandatory_defense') for r in records) for split in ('development','heldout')})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x',encoding='utf-8') as output:json.dump(payload,output,indent=2)
    print(json.dumps(dict(sha256=sha256_file(args.output),counts=payload['counts'],unknown=sum(r['proof']['status']=='unknown' for r in records))))


if __name__=='__main__':main()
