#!/usr/bin/env python3
"""Replay and provenance audit for local-order runs and controlled image probes."""
import argparse
import json
from pathlib import Path
from PIL import Image
import run_wedetect_shot_entities as io
from local_order_contract import plan,validate_extraction,compare_local
from run_local_order_refinement import clean_graph,image_index


def audit(root):
    state=io.read(root/'run.json');assert state['status']=='success',state
    for name,sha in io.read(root/'source_hashes.json').items():assert io.sha(root/'source_snapshot'/name)==sha
    for name,sha in io.read(root/'code_hashes.json').items():assert io.sha(root/'code_snapshot'/name)==sha
    source=root/'source_snapshot'
    graphs=[io.read(source/('graph_'+s+'.json')) for s in state['shots']]
    plans=[io.read(root/('plan_'+s+'.json')) for s in state['shots']]
    originals=io.read(source/'manifest.json')['images'];lookup={(f['shot_id'],f['frame_id']):f for f in originals}
    for f in io.read(root/'manifest.json')['images']:
        assert io.sha(f['path'])==f['sha256']
        if f['role']=='detail':
            parent=lookup[(f['shot_id'],f['frame_id'])]
            assert io.sha(parent['path'])==f['original_sha256']
            with Image.open(parent['path']) as original,Image.open(f['path']) as detail:
                crop=original.crop(f['original_region_xyxy']);crop=crop.resize((crop.width*2,crop.height*2),Image.Resampling.NEAREST)
                assert crop.size==detail.size and crop.tobytes()==detail.tobytes()
    extracts=[io.read(root/('local_'+s)/'response.json') for s in state['shots']]
    for g,p,e in zip(graphs,plans,extracts):
        assert p==plan(g);validate_extraction(e,p,g)
        payload=io.read(root/('local_'+g['shot_id'])/'input.json')
        assert payload['graph']==clean_graph(g) and payload['plan']==p
        assert 'relations' not in payload['graph'] and 'source' not in payload['graph']
    result=compare_local(graphs,plans,extracts,io.read(source/'alignment.json'),io.read(root/'review/response.json'),io.read(source/'policy.json'))
    assert result==io.read(root/'comparison.json')
    memory=io.read(root/'scene_memory.json')
    assert memory['baseline']==io.read(source/'scene_memory.json') and memory['local_comparison']==result
    assert memory['local_graphs']==extracts and memory['local_plans']==plans
    threads=[];usage=[];calls=[]
    for stage in ['local_'+s for s in state['shots']]+['review']:
        d=root/stage;req=io.read(d/'request.json')
        assert io.sha(d/'prompt.txt')==req['prompt_sha256'] and io.sha(d/'output.schema.json')==req['schema_sha256']
        assert io.read(d/'status.json')['status']=='success'
        usage+=io.audit_events(d/'events.jsonl')
        events=[json.loads(l) for l in (d/'events.jsonl').read_text().splitlines() if l]
        tids=[e['thread_id'] for e in events if e['type']=='thread.started'];assert len(tids)==1;threads+=tids
        if stage.startswith('local_'):assert {f['shot_id'] for f in req['images']}=={stage[6:]}
        calls.append(dict(stage=stage,thread_id=tids[0],images=len(req['images']),response_sha256=io.sha(d/'response.json')))
    assert len(set(threads))==len(threads)==3
    totals={k:sum(u.get(k,0) for u in usage) for k in ('input_tokens','output_tokens','cached_input_tokens')};totals['total_tokens']=totals['input_tokens']+totals['output_tokens']
    data=dict(status='pass',new_model_calls=3,usage=totals,stages=calls,summary=result['summary'],
        checks=['source and snapshot hashes','lossless crop reconstruction','single-shot isolation','schema and semantic witnesses','complete pair/axis/frame coverage','tool-free distinct model contexts','deterministic replay','baseline and new assertions preserved'],
        limitations='No measured natural-image accuracy; model-grounded center bounds remain qualitative.')
    io.dump(root/'audit.json',data);print(json.dumps(data,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);audit(p.parse_args().run.resolve())
