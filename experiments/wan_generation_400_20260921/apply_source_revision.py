#!/usr/bin/env python3
"""Atomically refresh three inputs and requeue their already-completed shots."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
import campaign

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'prompt_revision_20260922'

def main():
    assert not (OUT/'applied.json').exists(),'Already applied; never duplicate reruns'
    request=json.loads((OUT/'request.json').read_text())
    audit=json.loads((OUT/'tokenizer_audit.json').read_text())
    assert audit['status']=='pass' and audit['over_limit']==0
    assert audit['production_equals_untruncated']
    new={e['episode_id']:e for e in map(json.loads,(OUT/'revised_episodes.jsonl').read_text().splitlines())}
    ids=set(request['episode_ids']);assert set(new)==ids
    assert hashlib.sha256(Path(request['effective_input']).read_bytes()).hexdigest()==request['effective_input_sha256']
    journal=[];moved=[];published=False
    with campaign.queue_lock():
        original=json.loads((ROOT/'queue.json').read_text());q=copy.deepcopy(original)
        original_by_key={t['key']:t for t in original['tasks']}
        assert len(q['tasks'])==2000 and not (ROOT/'complete.json').exists()
        selected={e:[t for t in q['tasks'] if t['episode_id']==e] for e in ids}
        for eid,group in selected.items():
            assert len(group)==new[eid]['shot_count']
            assert all(t['status']=='pending' for t in group) or all(t['status']=='done' for t in group), (eid,[t['status'] for t in group])
            lookup={s['shot_id']:s for s in new[eid]['shots']}
            rerun=all(t['status']=='done' for t in group)
            journal.append(dict(episode_id=eid,rank=group[0]['rank'],stage=group[0]['stage'],shots=len(group),
                action='rerun_completed_episode' if rerun else 'refresh_before_first_generation'))
            for task in group:
                shot=lookup[task['shot_id']]
                assert Path(shot['prompt_file']).read_text()==shot['wan_prompt_en']
                task.update(prompt=shot['wan_prompt_en'],prompt_sha256=shot['wan_sha256'],
                    prompt_source_revision='source_revision_20260922',
                    effective_input=request['effective_input'])
                if rerun:
                    task.update(status='pending',attempts=0,revision_queued_at=time.time(),
                        prior_revision_task_snapshot=str((OUT/'queue_before_apply.json').resolve()))
                    for key in ['worker','started','ended','result','error']:
                        task.pop(key,None)
        for task in q['tasks']:
            before=original_by_key[task['key']]
            assert all(task[k]==before[k] for k in ['key','episode_id','shot_id','rank','stage','seed'])
            if task['episode_id'] not in ids:assert task==before
        assert sum(x['action']=='rerun_completed_episode' for x in journal)==1
        assert sum(x['shots'] for x in journal if x['action']=='rerun_completed_episode')==6
        campaign.write_json(OUT/'queue_before_apply.json',original)
        q['source_revision']=dict(id='source_revision_20260922',episode_ids=sorted(ids),
            effective_input=request['effective_input'],effective_input_sha256=request['effective_input_sha256'],applied=time.time())
        try:
            for entry in journal:
                if entry['action']!='rerun_completed_episode':continue
                eid=entry['episode_id'];old=ROOT/'videos'/eid
                archive=OUT/'archived_videos'/'source_v1'/eid
                archive.parent.mkdir(parents=True,exist_ok=True)
                assert old.is_dir() and (old/'episode.json').exists() and not archive.exists()
                with (old/'concat.lock').open('a') as lock:
                    fcntl.flock(lock,fcntl.LOCK_EX)
                    files=[dict(name=p.name,bytes=p.stat().st_size) for p in old.iterdir() if p.is_file()]
                    os.rename(old,archive);moved.append((old,archive));old.mkdir()
                entry.update(archive=str(archive.resolve()),archived_files=files)
            campaign.write_json(ROOT/'queue.json',q);published=True
        except BaseException:
            if not published:
                for old,archive in reversed(moved):
                    if old.exists():old.rmdir()
                    os.rename(archive,old)
            raise
        result=dict(status='applied',applied=time.time(),episodes=journal,
            task_count=2000,unique_episode_count=400,other_397_episodes_unchanged=True,
            priorities_and_seeds_unchanged=True,prompt_source_revision='source_revision_20260922',
            regenerated_shots_queued=6,pending_shots_refreshed=12,
            effective_input=request['effective_input'],effective_input_sha256=request['effective_input_sha256'])
        campaign.write_json(OUT/'applied.json',result)
        manifest=json.loads((ROOT/'manifest.json').read_text())
        manifest['effective_source']=request['effective_input']
        manifest['effective_source_sha256']=request['effective_input_sha256']
        manifest['source_revision_journal']=str((OUT/'applied.json').resolve())
        campaign.write_json(ROOT/'manifest.json',manifest)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
