"""Sequential staged Nu research campaign. No automatic strength or parity claims."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from evidence import atomic_json, digest
from learning import index_corpus
from collect import storage_guard
from train import resource_guard

TOOLS=Path(__file__).resolve().parent
ROOT=TOOLS.parents[1]

def invoke(script, *arguments):
    resource_guard();storage_guard(ROOT)
    subprocess.run([sys.executable,str(TOOLS/script),*[str(value) for value in arguments]],check=True)

def matches(args, model, output, games, seed, incumbent=False):
    if output.exists():
        report=json.loads(output.read_text())
        if not report.get('completed') or report.get('rejected'):raise RuntimeError('preserved incomplete/rejected match needs a new evidence directory')
        if report['model_sha256']!=digest(model) or report['engine_sha256']!=digest(args.engine):raise RuntimeError('match evidence artifact mismatch')
        expected=dict(opponent_sha256=digest(args.engine if incumbent else args.opponent),
                      expected_games=games,seed_base=seed,threads=args.threads,
                      milliseconds=250,internal_ms=230,cap=160,threat_plies=0,lmr=False)
        if any(report.get(key)!=value for key,value in expected.items()):
            raise RuntimeError('match evidence opponent/configuration mismatch')
        if report.get('opponent_model_sha256')!=(digest(args.incumbent) if incumbent else None):
            raise RuntimeError('match evidence incumbent model mismatch')
        return report
    extra=['--opponent-model',args.incumbent] if incumbent else []
    invoke('arena.py','--engine',args.engine,'--model',model,'--opponent',args.engine if incumbent else args.opponent,
           '--games',games,'--seed-base',seed,'--threads',args.threads,'--output',output,*extra)
    return json.loads(output.read_text())

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--engine',type=Path,default=ROOT/'build-nu/nu.exe')
    p.add_argument('--teacher',type=Path,default=ROOT/'.tmp/nu-teacher-build/release/nu_offline_teacher.exe')
    p.add_argument('--opponent',type=Path,default=ROOT/'.tmp/nu-nokamute/target/release/nokamute.exe')
    p.add_argument('--incumbent',type=Path,required=True);p.add_argument('--directory',type=Path,required=True)
    p.add_argument('--stages',type=int,nargs='+',default=[10000,50000,200000])
    p.add_argument('--threads',type=int,default=1);p.add_argument('--epochs',type=int,default=24)
    p.add_argument('--slice-seconds',type=int,default=1800);p.add_argument('--no-qualification',action='store_true')
    p.add_argument('--ablations',action='store_true')
    args=p.parse_args()
    if not 1<=args.threads<=12 or args.stages!=sorted(set(args.stages)) or not all(100<=n<=200000 for n in args.stages):p.error('ordered bounded stages and 1..12 threads required')
    identity=dict(engine=digest(args.engine),teacher=digest(args.teacher),opponent=digest(args.opponent),
                  incumbent=digest(args.incumbent),threads=args.threads,epochs=args.epochs,stages=args.stages,ablations=args.ablations)
    args.directory.mkdir(parents=True,exist_ok=True);state=args.directory/'campaign.json'
    if state.exists():
        progress=json.loads(state.read_text())
        if progress['identity']!=identity:raise RuntimeError('campaign artifacts/configuration changed; start a new campaign directory')
    else:progress=dict(identity=identity,stages=[],completed=False);atomic_json(state,progress)
    for target in args.stages:
        if any(item['target']==target for item in progress['stages']):continue
        stage=args.directory/f'stage-{target}';stage.mkdir(exist_ok=True)
        corpus=stage/'corpus';index=stage/'positions.sqlite';inputs=stage/'inputs.json'
        source=Path(progress['stages'][-1]['selected']) if progress['stages'] else args.incumbent
        previous_files=[file for item in progress['stages'] for file in (args.directory/f"stage-{item['target']}"/'corpus').glob('game-*.jsonl')]
        raw_target=target*2
        if not index.exists():
            invoke('collect.py','--engine',args.engine,'--teacher',args.teacher,'--directory',corpus,
                   '--positions',raw_target,'--source-model',source,'--seed',99173+target,
                   '--milliseconds',20 if target<=10000 else 50 if target<=50000 else 100,'--wall-seconds',args.slice_seconds)
            count=json.loads((corpus/'manifest.json').read_text())['positions']
            if count<raw_target:
                progress['waiting']=f'collecting {target}: {count} raw positions';atomic_json(state,progress);return
            atomic_json(inputs,[str(file.resolve()) for file in previous_files+sorted(corpus.glob('game-*.jsonl'))])
            db=index_corpus([Path(file) for file in json.loads(inputs.read_text())],index);db.close()
        db=__import__('sqlite3').connect(index)
        accepted=db.execute('select count(*) from samples').fetchone()[0];db.close()
        if accepted<target:
            progress['waiting']=f'only {accepted} leakage-controlled positions; new corpus stage required';atomic_json(state,progress);return
        models=stage/'models'
        invoke('learning.py','--data-manifest',inputs,'--index',index,'--output',models,'--epochs',args.epochs,'--wall-seconds',args.slice_seconds)
        if not json.loads((models/'progress.json').read_text())['completed']:
            progress['waiting']=f'training {target} checkpoint saved';atomic_json(state,progress);return
        results=[]
        for model in sorted(models.glob('*.nnue')):
            inference=stage/(model.stem+'.inference.json')
            if not inference.exists():
                verified=subprocess.run([sys.executable,str(TOOLS/'verify_model.py'),str(model),'--engine',str(args.engine)],check=True,capture_output=True,text=True)
                atomic_json(inference,dict(json.loads(verified.stdout.strip().splitlines()[-1]),model_sha256=digest(model),engine_sha256=digest(args.engine)))
            else:
                check=json.loads(inference.read_text())
                if check['model_sha256']!=digest(model) or check['engine_sha256']!=digest(args.engine):raise RuntimeError('inference evidence artifact mismatch')
            report=matches(args,model,stage/(model.stem+'.development.json'),20,71000)
            results.append((report['points'],model))
        points,chosen=max(results,key=lambda entry:entry[0])
        summary=json.loads(chosen.with_suffix('.json').read_text())
        if summary['natural_games'][0]>=500 and summary['natural_games'][1]>=100:
            fine=stage/'outcome-models'
            invoke('learning.py','--data-manifest',inputs,'--index',index,'--output',fine,'--epochs',8,
                   '--widths',summary['width'],'--heads',summary['head'],'--outcome-only','--initialize',chosen.with_suffix('.pt'),
                   '--learning-rate',.0002,'--wall-seconds',args.slice_seconds)
            if not json.loads((fine/'progress.json').read_text())['completed']:
                progress['waiting']=f'outcome fine-tuning {target} checkpoint saved';atomic_json(state,progress);return
            model=next(fine.glob('*.nnue'))
            invoke('verify_model.py',model,'--engine',args.engine)
            fine_result=matches(args,model,stage/'outcome-development.json',20,71000)
            if fine_result['points']>points:points,chosen=fine_result['points'],model
        result=dict(target=target,accepted_positions=accepted,selected=str(chosen),development_points=points,qualified=False)
        if args.ablations:
            report=json.loads(chosen.with_suffix('.json').read_text())
            for group in ('identity','mobility','pinning','stack','gates','queen'):
                invoke('learning.py','--data-manifest',inputs,'--index',index,'--output',stage/f'ablation-{group}',
                       '--widths',report['width'],'--heads',report['head'],'--epochs',args.epochs,'--ablate',group,'--wall-seconds',args.slice_seconds)
                if not json.loads((stage/f'ablation-{group}'/'progress.json').read_text())['completed']:
                    progress['waiting']=f'ablation {group} at {target} checkpoint saved'
                    atomic_json(state,progress);return
        if points>11:
            confirm=matches(args,chosen,stage/'confirmation.json',100,92000)
            incumbent=matches(args,chosen,stage/'incumbent.json',20,112000,True)
            if confirm['points']>55 and incumbent['points']>=10 and not args.no_qualification:
                invoke('qualify.py','--engine',args.engine,'--model',chosen,'--opponent',args.opponent,
                       '--development',stage/'confirmation.json','--incumbent-match',stage/'incumbent.json','--directory',stage/'qualification')
                result['qualified']=json.loads((stage/'qualification/qualification.json').read_text())['passed']
                progress['stages'].append(result);progress['completed']=True;atomic_json(state,progress);return
        if not any(s['target']==target for s in progress['stages']):progress['stages'].append(result)
        atomic_json(state,progress)
    progress.update(completed=True,waiting=None);atomic_json(state,progress)

if __name__=='__main__':main()
