#!/usr/bin/env python3
"""Audit frozen inputs, fresh tool-free stages, reproducible scoring and prompt separation."""
import argparse,hashlib,json
from pathlib import Path
import run_wedetect_shot_entities as io
from run_isolated_shot_static_3d import owned_compute_job
from score_gs_consistency import score

def audit(root):
    owned_compute_job();read=lambda n:json.loads((root/n).read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    manifest=read('manifest.json');payload=read('payload.json');failures=[];calls=[]
    for s in manifest['sources']:
        if sha(Path(s['path']))!=s['sha256']:failures.append('changed source '+s['path'])
    for name,key in [('graph_a.json',0),('graph_b.json',1)]:
        if sha(root/name)!=manifest['sources'][key]['sha256']:failures.append('graph snapshot differs')
    for name,h in read('code_hashes.json').items():
        if sha(root/'code_snapshot'/name)!=h:failures.append('snapshot changed '+name)
    # Only sanitized graph data/images are supplied; never the source manifest, paths or historical judgments.
    text=json.dumps(payload,ensure_ascii=False)
    for token in ['study_inconsistent','/vast/','source_path','agent_review','expected_anomalies']:
        if token in text:failures.append('prompt provenance leakage '+token)
    for stage in ['matching','witness','verification']+(['recheck'] if (root/'recheck').exists() else []):
        d=root/stage;req=json.loads((d/'request.json').read_text());status=json.loads((d/'status.json').read_text())
        if status['status']!='success':failures.append('failed call '+stage)
        if sha(d/'prompt.txt')!=req['prompt_sha256'] or sha(d/'output.schema.json')!=req['schema_sha256']:failures.append('request modified '+stage)
        if req['images']!=manifest['images']:failures.append('wrong images '+stage)
        command=req['command']
        for flag in ['--ephemeral','--ignore-user-config','--skip-git-repo-check']:
            if flag not in command:failures.append('nonisolated '+stage)
        usage=io.audit_events(d/'events.jsonl');calls.append(dict(stage=stage,usage=usage))
    if read('witness/input.json')!=read('verification/input.json'):failures.append('reviewer inputs differ')
    result=score([read('graph_a.json'),read('graph_b.json')],read('matching.json'),read('geometry_diagnostics.json'),[read('witness/response.json'),read('verification/response.json')]+([read('recheck/response.json')] if (root/'recheck/response.json').exists() else []),payload['images'])
    if result!=read('score.json'):failures.append('score not replayable')
    report=dict(passed=not failures,failures=failures,calls=calls,source_count=len(manifest['sources']),
                checked='source and code hashes; sanitized payload; fresh tool-free service calls; identical independent review inputs; exact deterministic score replay',
                limitation='Protocol audit does not independently certify the visual claims, model identity matching, or physical ground truth.')
    (root/'audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps(report,ensure_ascii=False))
    if failures:raise ValueError(failures)
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);audit(p.parse_args().run.resolve())
