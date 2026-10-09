"""Re-encode saved positions without changing labels, splits or provenance."""
import argparse
import json
from pathlib import Path
from train import response
from genseki.uhp import UhpProcess

def main():
    p=argparse.ArgumentParser();p.add_argument('--engine',required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--schema',type=int,choices=(1,2,3,4,5,6,7,8),default=3)
    args=p.parse_args();engine=UhpProcess([args.engine,'--feature-schema',str(args.schema)])
    schema=int(response(engine,'nu-feature-schema')[0])
    def features(position):
        response(engine,'nu-loadposition '+position)
        return ([list(map(int,line.split(':')[1].split())) for line in response(engine,'nu-features')[:2]],int(response(engine,'nu-prior')[0]) if schema in (5,7,8) else 0)
    try:
        with args.input.open() as source,args.output.open('x') as output:
            for line in source:
                row=json.loads(line)
                row['features'],prior=features(row['position']);row['feature_schema']=schema
                if schema in (5,7,8):row.update(prior_white=prior,strategic_prior_version=1)
                else:
                    row.pop('prior_white',None);row.pop('strategic_prior_version',None)
                # Preference children require their source coordinates, which v2 did not save.
                # Preserve outcome supervision rather than silently misencode old feature IDs.
                if 'preferred_position' in row:
                    row['preferred_features'],row['preferred_prior_white']=features(row['preferred_position'])
                    row['alternative_features'],row['alternative_prior_white']=features(row['alternative_position'])
                else:
                    row.pop('preferred_features',None);row.pop('alternative_features',None)
                candidates=row.get('alternatives',[])
                if all('position' in candidate for candidate in candidates):
                    for candidate in candidates:
                        candidate['features'],candidate['prior_white']=features(candidate['position'])
                else:
                    row.pop('alternatives',None)
                if schema not in (5,7,8):
                    row.pop('preferred_prior_white',None);row.pop('alternative_prior_white',None)
                    for candidate in row.get('alternatives',[]):candidate.pop('prior_white',None)
                output.write(json.dumps(row)+'\n')
    finally:engine.close()
if __name__=='__main__':
    from research_job import run
    run(main)
