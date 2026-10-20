from pathlib import Path
import sys,json
r=Path(__file__).resolve().parent;sys.path.insert(0,str(r/'runtime/EECBench/scripts'))
import build_three_method_static_scenes as f
f.LABELS=r/'study0/static';f.BOXER=r/'study0/geometry'
a,_=f.build('boxer_geocalib','shot1');b=json.loads((r/'study0/fusion/shot1/Gs_global.json').read_text());a.pop('provenance');b.pop('provenance')
diffs=[]
def compare(a,b,path=''):
 if isinstance(a,dict):
  for k in a:compare(a[k],b[k],path+'/'+k)
 elif isinstance(a,list):
  for i,(x,y) in enumerate(zip(a,b)):compare(x,y,path+'/'+str(i))
 elif a!=b:diffs.append((path,a,b))
compare(a,b);print('DIFFCOUNT',len(diffs));print(diffs[:15]);print('MAXDIFF',max((abs(a-b) for _,a,b in diffs if isinstance(a,(float,int)) and isinstance(b,(float,int))),default=0))
