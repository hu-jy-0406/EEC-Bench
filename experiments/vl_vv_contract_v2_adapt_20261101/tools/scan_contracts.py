import json,collections,subprocess,re,os
from pathlib import Path
R=Path('/vast/users/guangyi.chen/causal_group/jinyuan.hu/eec-bench/EECBench/experiments')
V=R/'episode_contracts_v2_20261029'; C=R/'contract_cleanup_20261031'
def sz(p): 
    return sum(f.stat().st_size for f in Path(p).rglob('*') if f.is_file())
print('v2 deliverables MB',sz(V/'deliverables')/1e6,'v2 episodes MB',sz(V/'episodes')/1e6,'cleanup deliverables MB',sz(C/'deliverables')/1e6,'cleanup episodes MB',sz(C/'episodes')/1e6)
# which files hold the field
for root,name in ((V/'deliverables','v2 deliv'),(V/'episodes','v2 work'),(C/'deliverables','cl deliv'),(C/'episodes','cl work'),(V/'pilot_history','v2 pilot'),(C/'pilot_history','cl pilot')):
    c=collections.Counter()
    for f in root.rglob('*'):
        if f.is_file() and f.stat().st_size<30_000_000:
            try: t=f.read_text()
            except Exception: continue
            if 'transition_from_previous' in t or '| transition:' in t: c[f.name if root.name!='deliverables' or f.parent.name!='deliverables' else f.name]+=1
    print(name,dict(c))
rows=[json.loads(l) for l in open(C/'deliverables/contracts_1_200.jsonl')]
all400=[json.loads(l) for l in open(V/'deliverables/contracts_400.jsonl')]
print(len(rows),len(all400), rows[0]['schema_version'], all400[0]['schema_version'], all400[0].keys())
cl={r['episode_id']:r for r in rows}
final=[cl.get(r['episode_id'],r) for r in all400]
cnt=collections.Counter(); keys=collections.Counter(); dims=collections.Counter(); ex=[]
tv=collections.Counter(); sfields=collections.Counter(); rqf=collections.Counter(); 
for c in final:
    for s in c['shots']:
        sfields.update(s.keys())
        tv[str(s['shot_description'].get('transition_from_previous'))]+=1
        sfields.update('sd.'+k for k in s['shot_description'])
        for d in ('appearance','spatial','motion'):
            for it in s[d]:
                rqf.update(f'{d}.{k}' for k in it)
                cnt[(d,'single' if len(it['entities'])==1 else 'multi' if it['entities'] else 'none')]+=1
                cnt[f'q:{it["quantifier"]}']+=1
        cnt['absent']+=len(s['absent'])
        cnt['loc%d'%len(s['locations'])]+=1
    for it in c['cross_shot']:
        keys.update(it.keys()); dims[it.get('dimension')]+=1
        cnt[('xs',len(it['entities']),len(it.get('shot_ids',[])))]+=1
        if len(ex)<14: ex.append((c['episode_id'],it))
print('tv',tv); print('sf',sfields); print('rqf',rqf); print('cnt',cnt); print('keys',keys); print('dims',dims)
for e in ex: print(json.dumps(e,ensure_ascii=False)[:420])
print('manifest shots', final[0]['shots'][0]['shot_id'])
# id in entities presence
bad=collections.Counter()
for c in final:
    ids=set(c['entity_descriptions'])
    pres=set(str(x) for s in c['shots'] for x in s['presence'])
    ab=set(str(x) for s in c['shots'] for x in s['absent'])
    bad['entities_not_in_any_presence']+=len(ids-pres)
    bad['absent_only']+=len((ids-pres)&ab)
    names=[e['name'] for e in c['entity_descriptions'].values()]
    bad['dupnames']+=len(names)-len(set(names))
    labs=collections.Counter(e['label'] for e in c['entity_descriptions'].values())
    for s in c['shots']:
        for d in ('appearance','spatial','motion'):
            for it in s[d]:
                for k in it['entities']:
                    if k not in s['presence']: bad['req_entity_not_in_presence:'+('absent' if k in s['absent'] else 'not_listed')]+=1
print(bad)
