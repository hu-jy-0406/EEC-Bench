"""Lossless JSON transport: repeated subtrees and homogeneous row tables."""
import json
from collections import Counter
VERSION='lossless_tables_refs_v1'
GUIDE='''INPUT_ENCODING: The JSON below is a lossless representation of the usual INPUT_JSON. `data` is its root. {"$ref":"dN"} means substitute shared[dN]. {"$table":{"columns":[...],"rows":[...]}} means a list of objects: zip each row with the columns, recursively expanding values. All numbers, strings, rows, frames and evidence are unchanged; references share data, never entity identity. Read all applicable evidence normally. Output the original required schema, not this transport format.\n'''
def dump(x):return json.dumps(x,ensure_ascii=False,separators=(',',':'),allow_nan=False)
def pack(payload):
 counts=Counter()
 def scan(x):
  if isinstance(x,(dict,list)):
   k=dump(x)
   if len(k)>=240:counts[k]+=1
  if isinstance(x,dict):
   assert not any(k.startswith('$') for k in x),'Reserved wire key in source'
   for v in x.values():scan(v)
  elif isinstance(x,list):
   for v in x:scan(v)
 scan(payload);chosen={k for k,n in counts.items() if n>=2 and (n-1)*len(k)-30*n>100};ids={};shared={}
 def encode(x,intern=True):
  if intern and isinstance(x,(dict,list)):
   k=dump(x)
   if k in chosen:
    if k not in ids:
     ref='d'+str(len(ids));ids[k]=ref;shared[ref]=encode(x,False)
    return {'$ref':ids[k]}
  if isinstance(x,dict):return {k:encode(v) for k,v in x.items()}
  if isinstance(x,list):
   if len(x)>=3 and all(isinstance(r,dict) for r in x):
    columns=list(x[0]);valid=all(list(r)==columns for r in x)
    if valid:
     plain=[encode(r) for r in x];table={'$table':{'columns':columns,'rows':[[encode(r[k]) for k in columns] for r in x]}}
     if len(dump(table))<len(dump(plain)):return table
     return plain
   return [encode(v) for v in x]
  return x
 data=encode(payload);wire=dict(encoding=VERSION,shared=shared,data=data)
 # Remove definitions created by an unselected table representation.
 reached=set()
 def visit(v):
  if isinstance(v,dict):
   if set(v)=={'$ref'}:
    r=v['$ref']
    if r not in reached:reached.add(r);visit(shared[r])
   else:
    for x in v.values():visit(x)
  elif isinstance(v,list):
   for x in v:visit(x)
 visit(data);wire['shared']={k:v for k,v in shared.items() if k in reached}
 assert unpack(wire)==payload
 return wire
def unpack(wire):
 assert wire['encoding']==VERSION
 shared=wire['shared'];active=set()
 def decode(x):
  if isinstance(x,dict):
   if set(x)=={'$ref'}:
    r=x['$ref'];assert r not in active,'Reference cycle';active.add(r);v=decode(shared[r]);active.remove(r);return v
   if set(x)=={'$table'}:
    t=x['$table'];cols=t['columns'];assert len(set(cols))==len(cols)
    result=[]
    for row in t['rows']:
     assert len(row)==len(cols);result.append({k:decode(v) for k,v in zip(cols,row)})
    return result
   return {k:decode(v) for k,v in x.items()}
  if isinstance(x,list):return [decode(v) for v in x]
  return x
 return decode(wire['data'])
