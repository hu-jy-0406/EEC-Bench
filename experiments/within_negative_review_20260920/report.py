"""Audit complete fresh runs and keep isolated component costs separate."""
import csv,hashlib,json,sys
from pathlib import Path
R=Path(__file__).resolve().parent;B=R.parents[1]
sys.path.insert(0,str(B/'experiments/shot_binary_motion_20260920'))
from costs import usage,total
read=lambda p:json.loads(Path(p).read_text())
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
save=lambda p,x:Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
old=read(B/'experiments/shot_binary_motion_20260920/cost_summary.json')
screen=read(R/'screen_cost.json')
rows=[];events=[];stages=[]
for study in ('study2','study3','study4'):
    c=R/'full'/study
    if not (c/'summary.json').exists():continue
    summary=read(c/'summary.json')
    if summary['status']!='success':continue
    calls=[usage(c/r['call']/'status.json') for r in summary['calls']]
    assert all(r['status']=='success' for r in calls)
    assert total(calls)['tokens']==summary['total_tokens']
    assert sum(r['total_tokens'] for r in summary['stages'])==summary['total_tokens']
    assert all(sha(f['path'])==f['sha256'] for s in read(c/'raw_manifest.json')['shots'] for f in s['frames'])
    assert read(c/'entities/run.json')['detector_mode']=='fresh'
    names={e['entity_id']:e['name'] for sid in ('shot1','shot2','shot3') for e in read(c/'selected'/f'{sid}_scene.json')['entities']}
    match=read(c/'pairs/pair_000/matching.json')
    for g in match['groups']:names[g['group_id']]=' / '.join(dict.fromkeys(names[x] for x in g['a_ids']+g['b_ids']))
    fit=read(c/'pairs/pair_000/registration/roma_geometry/registration.json')['fits']['all_structures']
    assert fit['all_selected_pairs_used'] and fit['points_removed']==0 and fit['distance_power']==1 and fit['point_weights']=='uniform_1'
    scores={}
    for scope,result in list(summary['within_shots'].items())+list(summary['boundaries'].items()):
        within=scope.startswith('shot')
        if within:
            assert result['presence'] is None and not result['presence_evaluation_run']
            assert all(e['kind']=='spatial' and e['cosine']<0 for e in result['events'])
        spatial=result['spatial']['summary'];assert 'coverage' not in spatial
        assert spatial['total_pairs']==len(result['spatial']['units'])
        k=sum(u['status']=='conflict' for u in result['spatial']['units']);assert k==spatial['confirmed_conflict_pairs']
        if spatial['total_pairs']:assert abs(spatial['score']-100*(1-k/spatial['total_pairs']))<1e-9
        scores[scope]=dict(presence=None if within else result['presence']['summary'],spatial=spatial)
        for e in result['events']:
            ids=e.get('entity_ids',e.get('endpoint_groups',[e.get('group_id','')]))
            review=e.get('review',e.get('verification',{}))
            events.append(dict(study=study,scope=scope,event_id=e['event_id'],kind=e['kind'],status=e['status'],entities=' | '.join(names.get(x,x) for x in ids),cosine=e.get('cosine'),reason=review.get('reason',''),gate=e.get('gate_reason')))
    for s in summary['stages']:stages.append(dict(study=study,stage=s['stage'],seconds=s['seconds'],tokens=s['total_tokens']))
    rows.append(dict(study=study,elapsed_seconds=summary['elapsed_seconds'],calls=len(calls),usage=total(calls),within_usage=total([r for r in calls if Path(r['path']).parent.name.startswith('within_')]),scores=scores,entity_counts={sid:len(read(c/'selected'/f'{sid}_scene.json')['entities']) for sid in ['shot1','shot2','shot3']},source_hashes_unchanged=all(sha(p)==h for p,h in read(c/'provenance.json')['source_hashes'].items())))
compositions=[]
for o,n in zip(old['cases'],screen['cases']):
    assert o['study']==n['study']
    before=o['production_composition'];after={k:before[k]-n['before'][k]+n['after'][k] for k in before}
    compositions.append(dict(study=o['study'],before=before,after=after))
result=dict(scope='Fresh complete pipeline; component screen and frozen composition reported separately',fresh=rows,fresh_total=total([r['usage'] for r in rows]),screen=screen,composition=compositions,all_validation=total([screen['after']]+[r['usage'] for r in rows]),pricing=old['pricing'],events=events)
save(R/'results.json',result)
for name,data in [('events',events),('stages',stages)]:
    if data:
        with (R/(name+'.csv')).open('w') as f:
            w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
print(json.dumps({k:v for k,v in result.items() if k not in ('screen','events','composition')},ensure_ascii=False,indent=2))
