"""Re-encode saved positions without changing labels, splits or provenance."""
import argparse
import json
from pathlib import Path
from train import response
from genseki.uhp import UhpProcess

def main():
    p=argparse.ArgumentParser();p.add_argument('--engine',required=True);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();engine=UhpProcess([args.engine])
    schema=int(response(engine,'nu-feature-schema')[0])
    def features(position):
        response(engine,'nu-loadposition '+position)
        return [list(map(int,line.split(':')[1].split())) for line in response(engine,'nu-features')[:2]]
    try:
        with args.input.open() as source,args.output.open('x') as output:
            for line in source:
                row=json.loads(line)
                row['features']=features(row['position']);row['feature_schema']=schema
                # Preference children require their source coordinates, which v2 did not save.
                # Preserve outcome supervision rather than silently misencode old feature IDs.
                if 'preferred_position' in row:
                    row['preferred_features']=features(row['preferred_position'])
                    row['alternative_features']=features(row['alternative_position'])
                else:
                    row.pop('preferred_features',None);row.pop('alternative_features',None)
                candidates=row.get('alternatives',[])
                if all('position' in candidate for candidate in candidates):
                    for candidate in candidates:
                        candidate['features']=features(candidate['position'])
                else:
                    row.pop('alternatives',None)
                output.write(json.dumps(row)+'\n')
    finally:engine.close()
if __name__=='__main__':
    from research_job import run
    run(main)
