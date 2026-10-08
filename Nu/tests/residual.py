"""Schema 5 prior validation and deterministic residual resume."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import learning
row=dict(strategic_prior_version=1,prior_white=-145,preferred_prior_white=-40,alternative_prior_white=-100,
         preferred_features=[[],[]],preferred_position='G1|w|0|0|0|',alternative_position='G1|b|0|0|0|',alternatives=[dict(prior_white=75)])
learning.validate_prior(row)
assert learning.prior_for(row)==-145/600
assert learning.prior_for(row,'preferred_features')==-40/600
for change in ({'strategic_prior_version':True},{'strategic_prior_version':2},{'prior_white':None},{'prior_white':1801}):
    try:learning.validate_prior(dict(row,**change))
    except RuntimeError:pass
    else:raise AssertionError('bad residual contract accepted')
print('Nu schema 5 prior validation/orientation tests passed')
