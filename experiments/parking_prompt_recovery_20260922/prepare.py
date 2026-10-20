import json,sys,shutil
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1];sys.path.insert(0,str(B/'scripts'))
from run_wedetect_shot_entities import read,dump,sha
from gs_prompt_binding import validate_registry
src=R.parent/'multishot_registration_ab_20260922/shared/parking4';case=R/'case';case.mkdir(exist_ok=False)
for n in ['raw_manifest.json','narrative.json']:shutil.copy2(src/n,case/n)
# Reuse immutable original detector/clustering evidence; no copying old geometry or judgments.
shutil.copytree(src/'entities/shots',case/'entities/shots');shutil.copy2(src/'entities/manifest.json',case/'entities/manifest.json')
n=read(case/'narrative.json');shots=read(case/'raw_manifest.json')['shots'];sids=[s['shot_id'] for s in shots]
entries=[('brunette','Brunette woman','The brunette woman in a black cropped top.',sids,'Brunette woman'),('blonde','Blonde woman','The blonde woman with a high ponytail and olive-green sweater.',sids,'Blonde woman'),('mask','Hockey mask','The hand-held hockey mask; attribute changes do not create a different prompt instance.',sids,'Beige hockey mask'),('car','Dark car','The car beside the two women.',['Shot1','Shot3','Shot4'],'Dark car'),('pillar','P3 pillar','The yellow parking-garage pillar described as P3; color/text correctness is not a binding condition.',['Shot1','Shot2','Shot4'],'yellow P3 pillar'),('strap','Chain shoulder strap','The shoulder strap carried by the blonde woman; part scope, not entire handbag.',sids,'chain shoulder strap'),('necklace','Pendant necklace','The circular pendant necklace worn by the blonde woman.',['Shot3'],'delicate circular pendant'),('earrings','Small earrings','The small earrings worn by the blonde woman; prompt does not specify individual sides.',['Shot3'],'small earrings')]
entities=[]
for pid,name,desc,required,quote in entries:
 evidence=[dict(fact_id=f['fact_id'],quote=quote) for f in n['facts'] if quote in f['text']]
 assert evidence,(pid,quote)
 entities.append(dict(prompt_entity_id=pid,name=name,description=desc,evidence=evidence,schedule=[dict(shot_id=s,expectation='required' if s in required else 'not_required',reason='Explicitly described in this shot narrative.' if s in required else 'Not required by this shot text; not a prohibition.') for s in sids]))
registry=dict(schema_version='prompt_registry_v1',shot_ids=sids,entities=entities);validate_registry(registry,shots,n);dump(case/'prompt_registry.json',registry)
dump(R/'provenance.json',dict(source=str(src),reuse='raw detector and within-shot clustering only; no geometry/identity/scores reused',registry_source='Manually source-quoted normal shot prompts; frozen before new model calls',source_hashes={str(src/n):sha(src/n) for n in ['raw_manifest.json','narrative.json']}))
print(case)
