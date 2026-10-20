import sys,json
from pathlib import Path
B=Path(__file__).resolve().parents[2];sys.path.insert(0,str(B/'scripts'))
from gs_flow1_compact_payload import pack,dump
C=B/'experiments/study2_integrated_full_fresh_20260919/study2'
result={}
for f in sorted((C/'calls').glob('*/input.json')):
 d=json.loads(f.read_text());w=pack(d);r=json.loads((f.parent/'response.json').read_text())
 result[f.parent.name]=dict(original_chars=len(f.read_text()),compact_chars=len(dump(w)),top_fields={k:len(dump(v)) for k,v in d.items()},response_chars=len(dump(r)))
print(json.dumps(result,ensure_ascii=False,indent=2));Path(__file__).with_name('payload_profile.json').write_text(json.dumps(result,indent=2)+'\n')
