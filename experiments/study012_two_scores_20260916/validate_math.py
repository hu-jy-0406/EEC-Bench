import os,json,sys
from pathlib import Path
import numpy as np
H=Path(__file__).resolve().parent;os.environ['CASE_ROOT']=str(H/'study0');sys.path.insert(0,str(H))
from register import rz,params,ls_seed
from evaluate import score
from contracts import VERIFY
rng=np.random.default_rng(719);X=rng.normal(size=(30,3));R=rz(.91);s=1.7;t=np.array([3.,-1.,.7]);Y=s*X@R.T+t
found=ls_seed(X,Y);ss,RR,tt=params(found)
assert np.allclose(ss,s) and np.allclose(RR,R) and np.allclose(tt,t)
a,b=X[:2];va=(s*R@b+t)-(s*R@a+t);vb=s*R@(b-a)
assert np.allclose(va,vb)
assert np.isclose(va@vb/(np.linalg.norm(va)*np.linalg.norm(vb)),1)
assert np.isclose(va@(-vb)/(np.linalg.norm(va)*np.linalg.norm(vb)),-1)
assert score([{'status':'unknown'}])['score'] is None
r=score([{'status':s} for s in ['compatible','conflict','unknown','exempt']]);assert r['N']==3 and r['E']==1 and np.isclose(r['score'],200/3) and r['identification_interval']==[100/3,200/3]
assert 'prompt_motion_review' in VERIFY['properties']['relations']['items']['required']
(H/'math_contract_validation.json').write_text(json.dumps(dict(passed=True,checks=['known gravity Sim3 recovered from points','pair translation cancels','aligned direction cosine +1','one-sided reversal cosine -1','all unknown gives null','unknown denominator and exemption/interval','Prompt causal review schema mandatory']),indent=2))
print('Math/score/Prompt contract checks passed')
