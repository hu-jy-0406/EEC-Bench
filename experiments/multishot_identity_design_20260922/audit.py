import json,csv,hashlib,os,time,subprocess
from pathlib import Path
from collections import Counter,defaultdict
R=Path(__file__).resolve().parent;B=R.parents[1];W=B/'experiments/wan_generation_400_20260921';bundle=B/'exports/storymem_hf_priority50_20260922/storymem_inputs'
read=lambda p:json.loads(p.read_text())
save=lambda name,x:(R/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
p=W/'prompt_revision_20260922/input_queue_400.v2.jsonl';episodes=[json.loads(l) for l in p.read_text().splitlines() if l];index={e['episode_id']:e for e in read(bundle/'index.json')['episodes']};queue=read(W/'queue.json');tasks={t['key']:t for t in queue['tasks']};pause={e['episode_id']:e for e in read(W/'pause_20260922/completed_episodes.json')}
assert len(episodes)==len(index)==400
rows=[];scenes=[];gaps=[];hashes={str(p):sha(p),str(W/'queue.json'):sha(W/'queue.json'),str(bundle/'index.json'):sha(bundle/'index.json')}
for e in episodes:
 eid=e['episode_id'];entry=index[eid];contract_path=bundle/entry['contract_path'];assert sha(contract_path)==entry['contract_sha256'];c=read(contract_path)
 assert c['episode_id']==eid and e['shot_count']==len(e['shots'])==len(entry['shots'])
 mapping={s['shot_id']:s for s in entry['shots']};groups=defaultdict(list)
 for s in e['shots']:
  assert s['scene_id']==mapping[s['shot_id']]['source_scene_id'];assert tasks[eid+'/'+s['shot_id']]['prompt_sha256']==s['wan_sha256']
  groups[s['scene_id']].append(s['shot_id'])
 complete=all(tasks[eid+'/'+s['shot_id']]['status']=='done' for s in e['shots']);video=W/'videos'/eid/'episode.mp4';complete=complete and video.is_file() and (video.parent/'episode.json').is_file()
 if complete:assert eid in pause
 sizes=[len(ids) for ids in groups.values()];row=dict(episode_id=eid,rank=e['generation_priority'],episode_shots=e['shot_count'],scene_count=len(groups),max_scene_shots=max(sizes),qualifying_scenes=sum(n>=3 for n in sizes),scene_sizes=sizes,wan_complete=complete,video=str(video) if complete else None);rows.append(row)
 for scene,ids in groups.items():
  scenes.append(dict(episode_id=eid,rank=e['generation_priority'],scene_id=scene,shot_ids=ids,shot_count=len(ids),wan_complete=complete))
  if len(ids)<3:continue
  objects={sid:set(c['entity_schedule'][mapping[sid]['contract_schedule_key']]['objects']) for sid in ids}
  chars={sid:set(c['entity_schedule'][mapping[sid]['contract_schedule_key']]['characters']) for sid in ids}
  for kind,sets in [('object',objects),('character',chars)]:
   names=set.union(*sets.values())
   for name in names:
    present=[i for i,sid in enumerate(ids) if name in sets[sid]]
    for i,j in zip(present,present[1:]):
     if j-i<2:continue
     gaps.append(dict(episode_id=eid,rank=e['generation_priority'],scene_id=scene,scene_shots=len(ids),episode_shots=e['shot_count'],kind=kind,name=name,first_shot=ids[i],last_shot=ids[j],intervening=ids[i+1:j],wan_complete=complete))
def distribution(rs,ss):
 return dict(episodes=len(rs),shots=sum(r['episode_shots'] for r in rs),scenes=len(ss),episodes_with_scene_ge3=sum(r['max_scene_shots']>=3 for r in rs),scenes_ge3=sum(s['shot_count']>=3 for s in ss),episode_max_scene_shots=dict(sorted(Counter(r['max_scene_shots'] for r in rs).items())),scene_shot_counts=dict(sorted(Counter(s['shot_count'] for s in ss).items())),qualifying_episode_total_shots=dict(sorted(Counter(r['episode_shots'] for r in rs if r['max_scene_shots']>=3).items())),adjacent_pairs=sum(s['shot_count']-1 for s in ss),all_pairs=sum(s['shot_count']*(s['shot_count']-1)//2 for s in ss))
summary=dict(definition='Scene IDs from effective Wan inputs cross-checked against all 400 frozen source contracts/index; labels, not a visual audit of 400 generated videos.',all=distribution(rows,scenes),wan_complete=distribution([r for r in rows if r['wan_complete']],[s for s in scenes if s['wan_complete']]),scheduled_object_gap_episodes=len({g['episode_id'] for g in gaps if g['kind']=='object'}),completed_scheduled_object_gap_episodes=len({g['episode_id'] for g in gaps if g['kind']=='object' and g['wan_complete']}),source_hashes=hashes)
save('summary.json',summary);save('episode_rows.json',rows);save('scene_rows.json',scenes);save('schedule_gap_candidates.json',gaps)
for name,data in [('episodes.csv',rows),('scenes.csv',scenes),('schedule_gaps.csv',gaps)]:
 with (R/name).open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
by=defaultdict(list)
for g in gaps:
 if g['wan_complete'] and g['kind']=='object':by[g['episode_id']].append(g)
ranked=sorted(by,key=lambda eid:(next(r['episode_shots'] for r in rows if r['episode_id']==eid)!=4,-len(by[eid]),by[eid][0]['rank']))
for eid in ranked[:18]:print('CANDIDATE',json.dumps(dict(episode=eid,gaps=by[eid]),ensure_ascii=False),flush=True)
