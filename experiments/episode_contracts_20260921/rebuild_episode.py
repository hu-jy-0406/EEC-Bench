"""Fresh compilation/review for an explicitly revised source episode."""
import argparse,copy,json,time
import run

def details(data,src,error):
    fs={f['fact_id']:f['text'] for f in run.facts(src)};out=[str(error)]
    for item in data.get('entities',[])+data.get('claims',[]):
        for ev in item.get('evidence',[]):
            if ev.get('fact_id') not in fs or not ev.get('quote') or ev['quote'] not in fs[ev['fact_id']]:
                out.append('Nonliteral reference '+str(item.get('claim_id',item.get('label')))+': '+json.dumps(ev,ensure_ascii=False))
    claims={c['claim_id']:c for c in data.get('claims',[])}
    for c in claims.values():
        for dep in c['depends_on']:
            if dep not in claims or claims[dep]['shot_ids']!=c['shot_ids']:
                out.append('Bad dependency '+c['claim_id']+' '+json.dumps(c['shot_ids'])+' -> '+dep+' '+json.dumps(claims.get(dep,{}).get('shot_ids')))
    return '\n'.join(out)

def main():
    p=argparse.ArgumentParser();p.add_argument('episode_id');p.add_argument('--revision',default='source_v1');a=p.parse_args()
    run.io.safe_compute();run.DISABLED=run.io.disabled_skills_config();started=time.time()
    folder=run.HERE/'episodes'/a.episode_id;src=run.read(folder/'input.json')
    job=next(j for j in run.read(run.HERE/'manifest.json')['jobs'] if j['episode_id']==a.episode_id)
    assert run.sha(folder/'input.json')==job['input_sha256']
    assert all(run.read(q)['status']!='running' for q in (folder/'calls').glob('*/status.json'))
    try:
        for stage in ['draft','review']:
            if (folder/(stage+'.json')).exists():continue
            payload=copy.deepcopy(src)
            if stage=='review':payload['proposal']=run.read(folder/'draft.json')
            feedback=None
            for attempt in range(1,5):
                dest=folder/'calls'/f'{stage}_{a.revision}_{attempt}';result={}
                try:
                    raw=run.read(dest/'response.json') if (dest/'response.json').exists() else run.call(dest,payload,stage,feedback)
                    result=run.apply_review(payload['proposal'],raw) if stage=='review' else raw
                    run.validate(result,src)
                    run.dump(dest/'validation.json',dict(status='pass'));run.dump(folder/(stage+'.json'),raw)
                    if stage=='review':run.dump(folder/'final.json',result)
                    break
                except Exception as ex:
                    feedback=details(result,src,ex);run.dump(dest/'validation.json',dict(status='failed',error=feedback))
            else:raise RuntimeError(stage+' failed: '+feedback)
        final=run.validate(run.read(folder/'final.json'),src)
        assert final==run.validate(run.apply_review(run.read(folder/'draft.json'),run.read(folder/'review.json')),src)
        state=dict(episode_id=a.episode_id,status='success',claims=len(final['claims']),entities=len(final['entities']),seconds=time.time()-started,source_revision=a.revision)
    except Exception as ex:
        state=dict(episode_id=a.episode_id,status='failed',error=str(ex),seconds=time.time()-started,source_revision=a.revision)
    run.dump(folder/'status.json',state);print(json.dumps(state),flush=True)
    if state['status']=='failed':raise SystemExit(1)
if __name__=='__main__':main()
