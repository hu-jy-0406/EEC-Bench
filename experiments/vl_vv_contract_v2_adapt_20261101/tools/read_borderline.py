import json,re,sys
from pathlib import Path
HERE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(HERE.parents[1]/'scripts'))
import episode_contract as c
ids=[x.strip() for x in (HERE.parents[1]/'experiments/source_video_priority_20260921/generation_queue_400.ids.txt').read_text().splitlines() if x.strip()]
def sents(t): return [s.strip() for s in re.split(r'(?<=[.!?])\s+',t) if s.strip()]
want={11:['Shot1'],41:['Shot1','Shot2'],110:['Shot1'],118:['Shot1'],158:['Shot1'],259:['Shot1'],271:['Shot4'],8:['Shot3'],112:['Shot1'],389:['Shot2'],127:['Shot1']}
pat=re.compile(r'puppet|stylized|monochrome|muted|vintage|grainy|letterbox|painterly|pixel',re.I)
for i,shots in want.items():
    p=c.read(c.resolve_v2_contract(ids[i]))['prompt']
    print('##',i,ids[i],'| global:',p['global_prompt'][:150])
    for s in p['shots']:
        if s['shot_id'] in shots:
            print('  ',s['shot_id'],[x for x in sents(s['text']) if pat.search(x)][:3])
extra=re.compile(r'cinematic|painted|realistic|naturalistic|photographic|rendered in|rendering|\bfilm\b|\bink\b|pastel|gouache|charcoal|crayon|collage|lo-fi|low-poly|neon-noir|anime|manga|toon',re.I)
seen=set()
for l in open(HERE/'style_candidates.jsonl'): 
    r=json.loads(l); seen.add((r['episode_id'],r['source'],r['sentence']))
print('## extra')
for i,e in enumerate(ids):
    p=c.read(c.resolve_v2_contract(e))['prompt']
    for src,t in [('global',p['global_prompt'])]+[(s['shot_id'],s['text']) for s in p['shots']]:
        for x in sents(t):
            if (e,src,x) in seen: continue
            for m in extra.finditer(x):
                print(i,src[-5:],x[max(0,m.start()-45):m.end()+40]); break
