"""Export an already validated checkpoint without pretending training completed."""
import argparse
from pathlib import Path
from learning import make_network,atomic_checkpoint
from train import export,resource_guard
from evidence import atomic_json,digest

def main():
    import torch
    p=argparse.ArgumentParser();p.add_argument('--checkpoint',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    resource_guard();torch.set_num_threads(1)
    saved=torch.load(args.checkpoint,map_location='cpu',weights_only=True)
    state=saved.get('best_state')
    if state is None:raise RuntimeError('no completed held-out validation checkpoint')
    config=saved['config'];net=make_network(config['width'],config['head'],config['schema'])
    net.load_state_dict(state)
    if any(not torch.isfinite(v).all() for v in net.parameters()):raise RuntimeError('nonfinite checkpoint')
    args.output.parent.mkdir(parents=True,exist_ok=True);export(net,args.output)
    selected_updates=max((int(v.get('step',0)) for v in saved.get('best_optimizer',{}).get('state',{}).values()),default=0)
    atomic_checkpoint(args.output.with_suffix('.pt'),dict(state=state,config=config,selected_epoch=saved['selected']))
    atomic_json(args.output.with_suffix('.json'),dict(config=config,selected_epoch=saved['selected'],
               resume_updates=saved['updates'],selected_updates=selected_updates,validation_mse=saved['best_loss'],decision=saved.get('best_decision'),
               curves=saved.get('curves',[]),completed=False,source_checkpoint_sha256=digest(args.checkpoint),
               model_sha256=digest(args.output),reason='bounded partial-training validated checkpoint export'))

if __name__=='__main__':
    from research_job import run
    run(main)
