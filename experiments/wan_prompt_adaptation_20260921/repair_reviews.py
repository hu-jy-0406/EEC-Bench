#!/usr/bin/env python3
"""Targeted source-grounded correction; retain all prior model responses/history."""
import concurrent.futures
import copy
import importlib.util
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('wan_adapter',HERE/'run.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

def one(item):
    folder=HERE/'batches'/item['batch_id']
    src=m.read(folder/'input.json');old=m.read(folder/'final.json')
    wire=copy.deepcopy(src);wire['proposal']=old
    label=item.get('label','primary_source_check')
    for attempt in range(1,4):
        dest=folder/'calls'/f'review_{label}_{attempt}'
        feedback=item['feedback']
        if attempt>1: feedback+='\nCorrect the previous mechanical error: '+err
        try:
            if (dest/'response.json').exists():result=m.read(dest/'response.json')
            else:result=m.call(dest,wire,review=True,feedback=feedback)
            m.validate(result,src)
            m.dump(dest/'validation.json',dict(status='pass'))
            history=folder/'correction_history'/label
            m.dump(history/'previous_final.json',old)
            m.dump(history/'request.json',item)
            m.dump(history/'corrected_final.json',result)
            m.dump(folder/'review.json',result)
            m.dump(folder/'final.json',result)
            changed=[]
            for e,r in zip(old['episodes'],result['episodes']):
                for s,t in zip(e['shots'],r['shots']):
                    if s!=t:changed.append([e['episode_id'],s['shot_id']])
            m.dump(history/'audit.json',dict(changed_shots=changed,call=str(dest),source_protocol_unchanged=True))
            print(json.dumps(dict(batch=item['batch_id'],status='corrected',changed_shots=changed)),flush=True)
            return
        except Exception as e:
            err=str(e);m.dump(dest/'validation.json',dict(status='failed',error=err))
    raise ValueError(err)

if __name__=='__main__':
    m.io.safe_compute();m.verify_sources();m.DISABLED=m.io.disabled_skills_config()
    requests=m.read(HERE/'correction_requests.json')
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(one,requests))
    print(json.dumps({'completed_correction_batches':len(requests),'finished_at':time.time()}),flush=True)
