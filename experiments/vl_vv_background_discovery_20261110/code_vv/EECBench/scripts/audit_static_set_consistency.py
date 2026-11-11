#!/usr/bin/env python3
"""Replay real v1.3 inputs and audit exact scope, isolation and arithmetic."""
import argparse
import hashlib
import json
from pathlib import Path
from score_static_set_consistency import score
from run_isolated_shot_static_3d import owned_compute_job


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main(out):
    owned_compute_job()
    run=read(out/'run.json');assert run['status']=='success'
    graphs=[read(out/n) for n in ['graph_a.json','graph_b.json']]
    matching=read(out/'matching.json');policy=read(out/'policy.json')
    reviews=lambda prefix:[read(out/f'{prefix}_{i}/response.json') for i in [1,2]]
    actual=read(out/'score.json')
    replay=score(graphs,matching,policy,read(out/'auxiliary_inventories.json'),read(out/'queries.json'),
        read(out/'numeric_relations.json'),reviews('presence'),reviews('relations'),read(out/'image_index.json'))
    # Scorer admission tuples serialize as JSON arrays; compare in the saved
    # artifact domain so representation alone cannot invalidate exact replay.
    assert actual==json.loads(json.dumps(replay,ensure_ascii=False))
    manifest=read(out/'manifest.json')
    assert all(sha(Path(p))==v for p,v in manifest['sources'].items())
    assert all(sha(f['path'])==f['sha256'] for f in read(out/'images.json'))
    for name,h in read(out/'code_hashes.json').items():assert sha(out/'code_snapshot'/name)==h
    threads=[];usage=[]
    stages=['matching','policy','presence_1','presence_2','relations_1','relations_2']
    for stage in stages:
        status=read(out/stage/'status.json');assert status['status']=='success'
        for u in status['usage']:usage.append(dict(stage=stage,**u))
        ids=[e['thread_id'] for line in (out/stage/'events.jsonl').read_text().splitlines() if (e:=json.loads(line))['type']=='thread.started']
        assert len(ids)==1;threads+=ids
        request=read(out/stage/'request.json')
        assert sha(out/stage/'prompt.txt')==request['prompt_sha256']
        assert sha(out/stage/'output.schema.json')==request['schema_sha256']
        assert len(request['images'])==(0 if stage=='policy' else 12)
        payload=read(out/stage/'input.json')
        content=json.dumps(payload,ensure_ascii=False)
        for forbidden in ['study_inconsistent','expected_anomaly','previous_score','confirmed_relation_count','shared_yaw_refinement']:
            assert forbidden not in content, (stage,forbidden)
        if stage=='policy':
            assert set(payload)=={'groups','narrative_facts'}
            assert 'geometry' not in payload and 'images' not in payload
    assert len(set(threads))==6
    for branch in ['presence','relations']:
        assert read(out/f'{branch}_1/input.json')==read(out/f'{branch}_2/input.json')
        assert sha(out/f'{branch}_1/prompt.txt')==sha(out/f'{branch}_2/prompt.txt')
    policy_end=read(out/'policy/status.json')['ended']
    assert all(read(out/s/'status.json')['started']>=policy_end for s in stages[2:])
    units=actual['entity_results'];groupmap={g['group_id']:g for g in matching['groups']}
    for g in actual['confirmed_presence_groups']:assert groupmap[g]['identity']=='unmatched'
    for g in actual['confirmed_spatial_endpoint_groups']:assert groupmap[g]['identity']=='matched'
    assert not set(actual['confirmed_presence_groups'])&set(actual['confirmed_spatial_endpoint_groups'])
    # Independent arithmetic directly from saved rows, without metric().
    for section,rows in [('overall',units),('spatial_relations',actual['relation_results'])]:
        c=sum(r.get('weight',1) for r in rows if r['status']=='compatible')
        k=sum(r.get('weight',1) for r in rows if r['status']=='conflict')
        u=sum(r.get('weight',1) for r in rows if r['status']=='unknown')
        value=None if not c+k or not c+k+u else 100*(1-k/(c+k+u))
        assert actual[section]['score']==value
    audit=dict(status='pass',exact_score_replay=True,independent_score_arithmetic=True,
        source_and_image_hashes=True,snapshot_hashes=True,six_unique_fresh_contexts=True,
        isolated_reviews_equal_inputs=True,policy_before_verdicts_and_image_free=True,
        penalty_branches_disjoint_and_static_only=True,expected_labels_and_old_scores_not_supplied=True,
        stages=stages,usage=usage,total_input_tokens=sum(u['input_tokens'] for u in usage),
        total_output_tokens=sum(u['output_tokens'] for u in usage),
        browser_execution_tested=False,human_accuracy_validated=False)
    (out/'replay_audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);main(p.parse_args().out)
