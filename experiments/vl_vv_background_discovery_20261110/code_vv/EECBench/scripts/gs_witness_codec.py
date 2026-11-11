"""Reference repeated output witnesses without dropping canonical evidence."""
import copy
KEYS={'shot_id','frame_id','region_xyxy','observation'}
def is_witness(s):return s.get('type')=='object' and set(s.get('properties',{}))==KEYS

def schema_with_bank(schema,images):
 found=[False]
 def walk(s):
  if is_witness(s):found[0]=True;return {'type':'integer','minimum':0}
  out=copy.deepcopy(s)
  if 'properties' in out:out['properties']={k:walk(v) for k,v in out['properties'].items()}
  if 'items' in out:out['items']=walk(out['items'])
  for key in ['anyOf','oneOf','allOf']:
   if key in out:out[key]=[walk(x) for x in out[key]]
  return out
 out=walk(schema)
 if not found[0]:return out,False
 valid=[i+1 for i,f in enumerate(images) if f['frame_id']>=0]
 entry={'type':'object','additionalProperties':False,'required':['i','b','o'],'properties':{'i':{'type':'integer','enum':valid},'b':{'type':'array','items':{'type':'number'}},'o':{'type':'string'}}}
 out['properties']['witness_bank']={'type':'array','items':entry};out['required'].append('witness_bank')
 return out,True

def expand(value,schema,images):
 value=copy.deepcopy(value);bank=value.pop('witness_bank');used=set()
 def walk(v,s):
  if is_witness(s):
   assert type(v)==int and 0<=v<len(bank),'Invalid witness reference';used.add(v);r=bank[v];f=images[r['i']-1];assert f['frame_id']>=0,'Diagnostic image is not a witness'
   return dict(shot_id=f['shot_id'],frame_id=f['frame_id'],region_xyxy=r['b'],observation=r['o'])
  if s.get('type')=='object':return {k:walk(v[k],p) for k,p in s['properties'].items()}
  if s.get('type')=='array':return [walk(x,s['items']) for x in v]
  return v
 # Unreferenced bank rows remain in the saved wire response; they do not constitute a decision witness.
 # Missing/out-of-range references still fail, and canonical evidence gates remain mandatory.
 return walk(value,schema)
GUIDE='''\nWITNESS OUTPUT ENCODING: Every original-frame witness field is a zero-based integer reference into witness_bank. Each bank row is {i: 1-based original attachment index, b: original-pixel [x1,y1,x2,y2], o: short observation}. Reuse one bank row when frame, region and observation are the same across audit/check rows; different evidence must have different rows. Include every required witness and frame coverage. No unreferenced bank rows. The complete canonical witnesses are restored automatically. Prefer short factual observation labels. For straightforward unchanged entities, keep each rationale to a brief evidence-specific clause; use longer explanations wherever ambiguity, a split or motion causality needs it.\n'''
