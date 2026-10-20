#!/usr/bin/env python3
"""Build the human-check review site data for 20 randomly sampled episodes.

Sample: random.Random(20261003).sample(range(1, 201), 20) over generation
priorities of the first-200 multimodel run. For each episode and model it
collects the canonical prompt, the contract, the final scores, the confirmed
reviewed issues and one transcoded preview video (all shots concatenated in
order; 640 px wide, H.264 CRF 24, 16 fps, no audio). Sources are read only.
"""
import json
import random
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import imageio_ffmpeg

HERE = Path(__file__).resolve().parent
EXP = HERE.parent
WORKLIST = EXP / 'vl_vv_multimodel_first200_20260926/batch/worklist.jsonl'
SCORES = [EXP / 'vl_vv_multimodel_first200_run02/final_scores.jsonl',
          EXP / 'vl_vv_multimodel_first200_run02_b/final_scores.jsonl']
MODELS = ['wan21', 'cinetrans', 'wan22', 'storymem', 'holocine']
SEED = 20261003
FF = imageio_ffmpeg.get_ffmpeg_exe()
ENCODE = ['-vf', 'scale=640:-2,fps=16', '-c:v', 'libx264', '-preset', 'slow', '-crf', '24',
          '-pix_fmt', 'yuv420p', '-movflags', '+faststart', '-an']


def read(path):
    return json.loads(Path(path).read_text())


def transcode(task, target):
    sources = []
    for shot in task['shots']:
        if shot['source_video'] not in sources:
            sources.append(shot['source_video'])
    with tempfile.TemporaryDirectory() as tmp:
        listing = Path(tmp) / 'list.txt'
        listing.write_text(''.join(f"file '{s}'\n" for s in sources))
        subprocess.run([FF, '-v', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', str(listing)]
                       + ENCODE + [str(target)], check=True)
    return target.stat().st_size


def issues_for(score_row, names):
    review = read(score_row['scoring_result'].replace('episode_scoring/result.json', 'issue_review/result.json'))
    scoring = read(score_row['scoring_result'])
    deduction = {x['issue_id']: x for x in scoring['issue_scores']}
    out = []
    for bucket, rows in (('V-L', review['v_l_inconsistencies']),
                         ('V-V within', review['v_v_inconsistencies']['within_shot']),
                         ('V-V cross', review['v_v_inconsistencies']['cross_shot'])):
        for issue in rows:
            verdict = issue['review']['verdict']
            d = deduction.get(issue['issue_id'], {})
            out.append(dict(bucket=bucket, issue_id=issue['issue_id'], subcategory=issue['subcategory'],
                            verdict=verdict, severity=d.get('severity'),
                            deduction=d.get('adjusted_deduction'), duplicate_of=d.get('duplicate_of'),
                            description=issue['description'], critique=issue['review'].get('critique'),
                            entities=[names.get(e, e) for e in issue['entity_ids']],
                            shots=issue['scope_shot_ids']))
    return out


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    priorities = sorted(random.Random(SEED).sample(range(1, 201), 20))
    tasks = {(w['generation_priority'], w['model_id']): w
             for w in map(json.loads, WORKLIST.read_text().splitlines()) if w['generation_priority'] in priorities}
    scores = {(r['generation_priority'], r['model_id']): r
              for path in SCORES for r in map(json.loads, path.read_text().splitlines())}
    videos = HERE / 'site/videos'
    videos.mkdir(parents=True, exist_ok=True)
    jobs = [(tasks[(p, m)], videos / f'p{p:03d}_{m}.mp4') for p in priorities for m in MODELS]
    with ThreadPoolExecutor(workers) as pool:
        sizes = list(pool.map(lambda job: transcode(*job), jobs))
    episodes = []
    for p in priorities:
        first = tasks[(p, MODELS[0])]
        contracts = {tasks[(p, m)]['contract_sha256'] for m in MODELS}
        assert len(contracts) == 1, f'priority {p}: models received different contracts'
        models = []
        for m in MODELS:
            row = scores[(p, m)]
            ledger = read(Path(row['scoring_result']).parents[2] / 'work/case/episode_entities.json')
            names = {x['global_entity_id']: x['name'] for x in ledger['prompt_bound'] + ledger['prompt_unbound']}
            models.append(dict(model_id=m, model_name=row['model_name'], scores=row['scores'],
                               issue_counts=row['issue_counts'], video=f'videos/p{p:03d}_{m}.mp4',
                               issues=issues_for(row, names)))
        episodes.append(dict(priority=p, episode_id=first['episode_id'], shot_count=first['shot_count'],
                             duration=first['total_target_duration_seconds'],
                             prompt=read(first['canonical_prompt_path']), contract=read(first['contract_path']),
                             models=models))
    data = dict(seed=SEED, sampled_priorities=priorities, models=MODELS, episodes=episodes,
                video_encoding='all shots concatenated in order; 640 px wide, H.264 CRF 24, 16 fps, no audio')
    (HERE / 'site/data.json').write_text(json.dumps(data, ensure_ascii=False) + '\n')
    print('videos', len(sizes), 'MB', round(sum(sizes) / 1e6, 1), 'max MB', round(max(sizes) / 1e6, 2))


if __name__ == '__main__':
    main()
